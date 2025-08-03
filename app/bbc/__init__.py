import aiohttp
import asyncio
import logging
import json
import re
from bs4 import BeautifulSoup
from fastapi import APIRouter

bp = APIRouter(prefix="/bbc", tags=["BBC iPlayer"])

from app.bbc import routes

from .const import BBC_IPLAYER_BASE, BBC_MEDIA_SELECTOR

_LOGGER = logging.getLogger(__name__)

_CATEGORIES = []
_PROGRAMMES = []
_STREAMS = {}

def _parse_redux_script(soup: BeautifulSoup) -> dict | None:
    """Parse the Redux script from the BeautifulSoup object."""
    redux_script = soup.select_one("#tvip-script-app-store")
    if redux_script:
        _LOGGER.info("Found Redux script in BBC iPlayer page.")
        script = redux_script.get_text()
        match = re.search(r"window\.__IPLAYER_REDUX_STATE__ = ({.*?});", script, re.DOTALL)
        if match:
            try:
                redux_state = json.loads(match.group(1))
                _LOGGER.info("Parsed Redux state from BBC iPlayer page.")
                return redux_state
            except json.JSONDecodeError:
                _LOGGER.error("Failed to parse Redux state from BBC iPlayer page.")
    else:
        _LOGGER.warning("No Redux script found in BBC iPlayer page.")
    return None

async def reload_categories():
    """Async function to reload categories from the BBC iPlayer."""
    async with aiohttp.ClientSession() as session:
        response = await session.get(BBC_IPLAYER_BASE)
        if not response.ok:
            raise Exception("Failed to fetch categories from BBC iPlayer")
        html = await response.text()
        soup = BeautifulSoup(html, "html.parser")
        redux_script = _parse_redux_script(soup)
        if redux_script:
            nav_items: list = redux_script["navigation"]["items"]
            _CATEGORIES.clear()
            for item in nav_items:
                if item["id"] == "categories":
                    for subitem in item["subItems"]:
                        _CATEGORIES.append(subitem["id"])
            _LOGGER.info("Reloaded categories: %s", len(_CATEGORIES))

async def reload_programmes():
    """Async function to reload programmes from the BBC iPlayer."""
    async with aiohttp.ClientSession() as session:
        coros = [
            session.get(f"{BBC_IPLAYER_BASE}/categories/{category}/featured")
            for category in _CATEGORIES
        ]
        responses = await asyncio.gather(*coros)
        _LOGGER.info("Fetched cateogory data from BBC iPlayer.")
        for response in responses:
            if not response.ok:
                _LOGGER.error("Failed to fetch programmes for category: %s", response.url)
                continue
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            redux_script = _parse_redux_script(soup)
            if not redux_script:
                _LOGGER.error("Failed to parse Redux script for category: %s", response.url)
                continue
            for bundle in redux_script.get("bundles", []):
                for entity in bundle.get("entities", []):
                    if "episode" not in entity:
                        continue
                    if "live" not in entity["episode"]:
                        _LOGGER.warning("Episode entity missing 'live' key: %s", entity["episode"].get("id", "Unknown ID"))
                        continue
                    if not entity["episode"]["live"]:
                        continue
                    programme = {
                        "id": entity["episode"]["id"],
                        "title": entity["episode"]["title"]["default"],
                        "description": entity["episode"]["synopsis"].get("editorial", ""),
                        "image_backdrop": entity["episode"]["image"].get("default", ""),
                        "image_poster": entity["episode"]["image"].get("portrait", ""),
                        "category": entity["episode"]["labels"].get("category", ""),
                        "journey": entity["episode"].get("journey", None),
                    }
                    _PROGRAMMES.append(programme)
                    _LOGGER.info("Added programme: %s", programme["title"])
                    _STREAMS.clear()

async def get_streams(vid: str, version="3.0") -> dict | None:
    """Async function to get streams for a given video ID."""
    async with aiohttp.ClientSession() as session:
        response = await session.get(BBC_MEDIA_SELECTOR.format(VID=vid, VERSION=version))
        if not response.ok:
            _LOGGER.error("Failed to fetch streams for video ID: %s", vid)
            return None
        return await response.json()

async def get_programme_stream(pid: str, format: str="dash") -> str | None:
    """Async function to get a programme stream URL by ID."""
    if f"{pid}-{format}" in _STREAMS:
        return _STREAMS[f"{pid}-{format}"]
    async with aiohttp.ClientSession() as session:
        response = await session.get(f"{BBC_IPLAYER_BASE}/episode/{pid}")
        if not response.ok:
            _LOGGER.error("Failed to fetch stream URL for programme: %s", pid)
            return None
        html = await response.text()
        soup = BeautifulSoup(html, "html.parser")
        redux = _parse_redux_script(soup)
        if not redux:
            _LOGGER.error("Failed to parse Redux script for programme: %s", pid)
            return None
        if "versions" not in redux:
            _LOGGER.error("No versions found in Redux state for programme: %s", pid)
            return None
        if len(redux["versions"]) == 0:
            _LOGGER.error("No versions available for programme: %s", pid)
            return None
        vid = redux["versions"][0]["id"]
        if f"{vid}-{format}" in _STREAMS:
            return _STREAMS[f"{vid}-{format}"]
        mediaselector_version = "3.0"
        streams = None
        while True:
            streams = await get_streams(vid, version=mediaselector_version)
            if not streams:
                _LOGGER.error("Failed to fetch streams for video ID: %s - %s", vid, mediaselector_version)
                if mediaselector_version == "2.0":
                    break
                mediaselector_version = "2.0"
                continue
            break
        if not streams:
            return None
        if "error" in streams:
            _LOGGER.error("Error fetching streams: %s", streams["error"])
            return None
        if "media" not in streams:
            _LOGGER.error("Failed to fetch streams for video ID: %s", vid)
            return None
        video_media = [item for item in streams.get("media", []) if item.get("kind") == "video" or (item.get("type") or "").startswith("video/")]
        if not video_media:
            _LOGGER.error("No video media found for video ID: %s", vid)
            return None
        streams = [item for item in video_media[0].get("connection", []) if item.get("transferFormat") == format]
        if not streams:
            _LOGGER.error("No DASH streams found for video ID: %s", vid)
            return None
        stream_url = streams[0].get("href")
        if not stream_url:
            _LOGGER.error("No stream URL found for video ID: %s", vid)
            return None
        _STREAMS[f"{pid}-{format}"] = stream_url
        _STREAMS[f"{vid}-{format}"] = stream_url
        return stream_url
