import json
from fastapi import Response, Request
from fastapi.responses import RedirectResponse, JSONResponse
from urllib.parse import urlparse

from app.bbc import bp

@bp.get("/programmes")
def get_programmes() -> Response:
    """Get all programmes."""
    from app.bbc import _PROGRAMMES

    if not _PROGRAMMES:
        return Response("No programmes found", status_code=404)

    return JSONResponse(
        content=_PROGRAMMES,
        status_code=200,
    )

@bp.get("/commands/reload")
async def reload_commands() -> Response:
    """Reload BBC iPlayer categories and programmes."""
    from app.bbc import reload_categories, reload_programmes

    try:
        await reload_categories()
        await reload_programmes()
        return Response("Commands reloaded successfully", status_code=200)
    except Exception as e:
        return Response(f"Error reloading commands: {str(e)}", status_code=500)

@bp.get("/categories")
def get_categories() -> Response:
    """Get all categories."""
    from app.bbc import _CATEGORIES

    if not _CATEGORIES:
        return Response("No categories found", status_code=404)

    return Response(
        content=json.dumps(_CATEGORIES),
        status_code=200,
        media_type="application/json",
    )

@bp.get("/programmes/{pid}")
def get_programme(pid: str) -> Response:
    """Get a programme by ID."""
    from app.bbc import _PROGRAMMES, _STREAMS

    programme = next((p for p in _PROGRAMMES if p["id"] == pid), None)
    if not programme:
        return Response("Programme not found", status_code=404)

    programme["streams"] = next((v for k, v in _STREAMS.items() if pid in k), None)

    return Response(
        content=json.dumps(programme),
        status_code=200,
        media_type="application/json",
    )

@bp.get("/programmes/{pid}/episodes")
async def get_programme_episodes(pid: str) -> Response:
    """Get a programme episodes by ID."""
    from app.bbc import get_episodes
    episodes = await get_episodes(pid)
    if not episodes:
        return Response("Episodes not found", status_code=404)
    return Response(
        content=json.dumps(episodes),
        status_code=200,
        media_type="application/json",
    )

@bp.get("/programmes/{pid}/poster")
def get_programme_poster(pid: str) -> Response:
    """Get a programme poster by ID."""
    from app.bbc import _PROGRAMMES

    programme = next((p for p in _PROGRAMMES if p["id"] == pid), None)
    if not programme:
        return Response("Programme not found", status_code=404)

    if programme["image_poster"] is None:
        return Response("Poster not available", status_code=404)

    return RedirectResponse(
        url=programme["image_poster"].format(recipe="464x261"),
        status_code=301,
    )

@bp.get("/programmes/{pid}/stream/{eid}/{format}")
async def get_programme_stream(pid: str, eid: str, format: str) -> Response:
    """Get a programme stream by ID."""
    from app.bbc import _PROGRAMMES, get_programme_stream as gps


    programme = next((p for p in _PROGRAMMES if p["id"] == pid), None)
    if not programme:
        return Response("Programme not found", status_code=404)

    stream_url = await gps(pid, eid, format)
    if not stream_url:
        return Response("Stream URL not found", status_code=404)

    return RedirectResponse(
        url=stream_url,
        status_code=301,
    )


@bp.get("/programmes/{pid}/stream/{eid}/{subpath:path}")
async def get_programme_stream_path(pid: str, eid: str, subpath: str) -> Response:
    """Get a programme stream path by ID."""
    from app.bbc import get_programme_stream as gps

    stream_url = await gps(pid, eid)
    if not stream_url:
        return Response("Stream URL not found", status_code=404)

    parsed_url = urlparse(stream_url)
    # Replace the last part of the path of the parsed_url with subpath
    new_path = parsed_url.path.rsplit('/', 1)[0] + '/' + subpath
    new_url = parsed_url._replace(path=new_path).geturl()

    return RedirectResponse(
        url=new_url,
        status_code=301,
    )

@bp.get("/m3u/{format}")
async def get_m3u(request: Request, format: str) -> Response:
    """Get M3U playlist of all programmes."""
    from app.bbc import _PROGRAMMES, get_episodes

    # Get host header
    host = request.headers.get("host", "")

    m3u_content = "#EXTM3U\n"
    for programme in _PROGRAMMES:
        if not programme["live"]:
            continue
        await get_episodes(programme["id"])
        for episode in programme["episodes"]:
            if not episode["live"]:
                continue
            m3u_content += f"#EXTINF:-1 tvg-id=\"{episode['id']}\" tvg-name=\"{episode['title']}\" tvg-logo=\"http://{host}/bbc/programmes/{programme['id']}/poster\", {episode['title']}\n"
            # use this web service to forward to the stream via the programme ID
            m3u_content += f"http://{host}/bbc/programmes/{programme['id']}/stream/{episode['id']}/{format}\n"

    return Response(
        content=m3u_content,
        status_code=200,
        media_type="application/vnd.apple.mpegurl",
    )
