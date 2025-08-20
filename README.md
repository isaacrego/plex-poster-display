# Movie Poster Display (Plex)

Flask app in Docker to show Plex posters on a portrait 1080p display. Idle rotates artwork; when Plex is playing, shows the current item with a "Now Playing" banner.

## Run
```bash
docker compose up -d --build
```
Open `http://<NAS-IP>:9090/` and `http://<NAS-IP>:9090/config`.

## Notes
- Cache refresh every 30 min (re-shuffles idle list).
- Idle rotation interval is configurable (default 20s). Recommended 300s for fewer writes.
- Atomic cache writes and single Gunicorn worker to avoid file races.
- Now Playing detection reads `Player.state` and treats `playing` (and `buffering`) as active.

## Fill Modes
- Fill (Stretch), Crop, Fill Maintain Aspect

## Idle Rotation
- **Idle Rotation (seconds)** controls how long each idle poster stays up (default 20).

## Library Selection
- **Library (Section Key)**: numeric Plex section key (e.g., `5` for Movies). Blank = all movies/shows.

## Rating Filters
- Choose Critic or Audience rating and a threshold.

## MPAA Allowed
- G, PG, PG-13, R, NC-17, Unknown.


### Now Playing Behavior
- By default, **paused** counts as Now Playing (configurable in Poster settings).
- If multiple sessions are active, the app prefers **playing**, then **buffering**, then **paused**.
- If there are ties, it picks the session with the largest **viewOffset** (most progressed), then newest **updatedAt**.