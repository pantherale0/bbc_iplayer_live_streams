from typing import Any
import aiofiles
import aiohttp
import asyncio
import logging
import json
import re
from bs4 import BeautifulSoup
from fastapi import APIRouter

bp = APIRouter(prefix="/bbc", tags=["BBC iPlayer"])

from app import data_path
from app.bbc import routes

from .const import BBC_IPLAYER_BASE, BBC_MEDIA_SELECTOR

_LOGGER = logging.getLogger('uvicorn.error')

_STATE: dict[str, Any] = {}
_CATEGORIES: dict[str, dict] = {}
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
    global _STATE, _CATEGORIES
    async with aiofiles.open(f"{data_path}/state.json", "r", errors="ignore") as f:
        _STATE = json.loads(await f.read())
    if _STATE.get("category_last_refresh", 0) > asyncio.get_event_loop().time() - 3600:
        async with aiofiles.open(f"{data_path}/categories.json", "r") as f:
            _CATEGORIES = json.loads(await f.read())
        return
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
                        _CATEGORIES[subitem["id"]] = {}
                        # Get the first page to calculate length
                        category = await session.get(f"{BBC_IPLAYER_BASE}/categories/{subitem['id']}/a-z")
                        if category.ok:
                            html = await category.text()
                            soup = BeautifulSoup(html, "html.parser")
                            paging = soup.select_one(".pagination__list")
                            if paging:
                                _CATEGORIES[subitem["id"]]["total_pages"] = int(paging.find_all("li")[-1].find_next("span").find_next("span").text)
            _LOGGER.info("Reloaded categories: %s", len(_CATEGORIES))
            # Write to data
            async with aiofiles.open(f"{data_path}/categories.json", "w") as f:
                await f.write(json.dumps(_CATEGORIES))
            _STATE["category_last_refresh"] = asyncio.get_event_loop().time()
            async with aiofiles.open(f"{data_path}/state.json", "w") as f:
                await f.write(json.dumps(_STATE))

async def safe_download(url, sem, session) -> dict:
    async with sem:
        _LOGGER.info("Grabbing: %s", url)
        async with session.get(url) as response:
            return {
                "url": url,
                "ok": response.ok,
                "status": response.status,
                "text": await response.text()
            }

async def reload_programmes():
    """Async function to reload programmes from the BBC iPlayer."""
    global _STATE, _PROGRAMMES
    async with aiofiles.open(f"{data_path}/state.json", "r", errors="ignore") as f:
        _STATE = json.loads(await f.read())
    if _STATE.get("programme_last_refresh", 0) > asyncio.get_event_loop().time() - 3600:
        async with aiofiles.open(f"{data_path}/programmes.json", "r") as f:
            _PROGRAMMES = json.loads(await f.read())
        return
    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(15)
        coros = [
            asyncio.ensure_future(safe_download(f"{BBC_IPLAYER_BASE}/categories/{k}/a-z?page={i}", sem, session))
            for k, v in _CATEGORIES.items() for i in range(1, v['total_pages'])
        ]
        responses = await asyncio.gather(*coros)
        _LOGGER.info("Fetched cateogory data from BBC iPlayer.")
        for response in responses:
            if not response["ok"]:
                _LOGGER.error("Failed to fetch programmes for category: %s", response["url"])
                continue
            html = response["text"]
            soup = BeautifulSoup(html, "html.parser")
            redux_script = _parse_redux_script(soup)
            if not redux_script:
                _LOGGER.error("Failed to parse Redux script for category: %s", response["url"])
                continue
            for entity in redux_script["entities"].get("elements", []):
                if "live" not in entity:
                    _LOGGER.warning("Entity missing 'live' key: %s", entity["episode"].get("id", "Unknown ID"))
                    continue
                # Check if ID is already in _PROGRAMMES
                if next((p for p in _PROGRAMMES if p["id"] == entity["id"]), None):
                    continue
                programme = {
                    "id": entity["id"],
                    "title": entity["title"],
                    "description": entity["synopses"].get("small", ""),
                    "image_poster": entity["images"].get("standard", ""),
                    "category": redux_script["entities"]["category"].get("id", ""),
                    "live": entity["live"],
                    "episodes": []
                }
                _PROGRAMMES.append(programme)
                _LOGGER.info("Added programme: %s", programme["title"])
        # Write _PROGRAMMES to data as json
        async with aiofiles.open(f"{data_path}/programmes.json", "w") as f:
            await f.write(json.dumps(_PROGRAMMES))
        _STATE["programme_last_refresh"] = asyncio.get_event_loop().time()
        async with aiofiles.open(f"{data_path}/state.json", "w") as f:
            await f.write(json.dumps(_STATE))

def parse_episode_view(redux: dict, programme: dict) -> None:
    """Parse the episode view from the Redux state."""
    for episode in redux["entities"]["results"]:
        # Check if episode id is not already in programme
        if "episode" not in episode:
            continue
        if next((e for e in programme["episodes"] if e["id"] == episode["episode"]["id"]), None):
            continue
        if episode["episode"]["subtitle"] is not None:
            title = episode["episode"]["subtitle"]["default"]
        elif episode["episode"]["subtitle"] is None:
            title = episode["episode"]["title"]["default"]
        elif episode["episode"]["subtitle"]["slice"] is None:
            title = episode["episode"]["title"]["default"]
        else:
            title = f"{episode['episode']['title']['default']} - {episode['episode']['subtitle']['slice']}"
        programme["episodes"].append({
            "id": episode["episode"]["id"],
            "title": title,
            "description": episode["episode"]["synopsis"].get("small", ""),
            "live": episode["episode"]["live"]
        })

async def get_episodes(pid: str) -> list | None:
    """Async function to get episodes for a given programme ID."""
    async with aiohttp.ClientSession() as session:
        programme = next((p for p in _PROGRAMMES if p["id"] == pid), None)
        if not programme:
            _LOGGER.error("Programme not found: %s", pid)
            return None
        if _STATE.get(f"{pid}-episode-last-query", 0) > asyncio.get_event_loop().time() - 900:
            return programme["episodes"]
        programme_page = await session.get(f"{BBC_IPLAYER_BASE}/episodes/{pid}")
        if not programme_page.ok:
            _LOGGER.error("Failed to fetch episodes for programme: %s", pid)
            return None
        html = await programme_page.text()
        soup = BeautifulSoup(html, "html.parser")
        redux = _parse_redux_script(soup)
        if not redux:
            _LOGGER.error("Failed to extract redux state")
            return None
        if "entities" not in redux:
            _LOGGER.error("No entities found in redux state")
            return None
        parse_episode_view(redux, programme)
        sem = asyncio.Semaphore(15)
        coros = [
            asyncio.ensure_future(safe_download(f"{BBC_IPLAYER_BASE}/episodes/{pid}?seriesId={slice['id']}", sem, session))
            for slice in redux["header"]["availableSlices"]
        ]
        responses = await asyncio.gather(*coros)
        for response in responses:
            if not response["ok"]:
                _LOGGER.error("Failed to fetch episodes for series: %s", response["url"])
                continue
            soup = BeautifulSoup(response["text"], "html.parser")
            redux_slice = _parse_redux_script(soup)
            if not redux_slice:
                _LOGGER.error("Failed to extract redux state")
                continue
            parse_episode_view(redux_slice, programme)
        _STATE[f"{pid}-episode-last-query"] = asyncio.get_event_loop().time()
        return programme["episodes"]

async def get_streams(vid: str, version="3.0") -> dict | None:
    """Async function to get streams for a given video ID."""
    async with aiohttp.ClientSession() as session:
        response = await session.get(BBC_MEDIA_SELECTOR.format(VID=vid, VERSION=version))
        if not response.ok:
            _LOGGER.error("Failed to fetch streams for video ID: %s", vid)
            return None
        return await response.json()

async def get_programme_stream(pid: str, eid: str, format: str="dash") -> str | None:
    """Async function to get a programme stream URL by ID."""
    if f"{eid}-{format}" in _STREAMS:
        return _STREAMS[f"{eid}-{format}"]
    async with aiohttp.ClientSession() as session:
        response = await session.get(f"{BBC_IPLAYER_BASE}/episode/{eid}")
        if not response.ok:
            _LOGGER.error("Failed to fetch stream URL for programme: %s", eid)
            return None
        html = await response.text()
        soup = BeautifulSoup(html, "html.parser")
        redux = _parse_redux_script(soup)
        if not redux:
            _LOGGER.error("Failed to parse Redux script for programme: %s", eid)
            return None
        if "versions" not in redux:
            _LOGGER.error("No versions found in Redux state for programme: %s", eid)
            return None
        if len(redux["versions"]) == 0:
            _LOGGER.error("No versions available for programme: %s", eid)
            return None
        if redux["versions"][0]["kind"] == "simulcast":
            vid = redux["versions"][0]["serviceId"]
        else:
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
        _STREAMS[f"{eid}-{format}"] = stream_url
        _STREAMS[f"{vid}-{format}"] = stream_url
        return stream_url
