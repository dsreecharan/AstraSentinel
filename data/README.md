# Local source assets and fixtures

Put permissioned aerial MP4s in the local `data/demo_video/` directory. Keep source media and retained evidence private and use an authorized download or private handoff when redistribution is restricted. The deterministic synthetic fixtures in `backend/tests/fixtures/` are used by tests.

## Provenance and release inventory

| Asset | Origin and terms | Verified use and release status |
| --- | --- | --- |
| Aerial intersection excerpt | Matthias Groeneveld via Pexels. [Original video](https://www.pexels.com/video/aerial-view-of-busy-urban-intersection-35172060/) · [License](https://www.pexels.com/license/) · [Terms](https://www.pexels.com/terms-of-service/) | Four-second, 10 FPS local replay and CPU benchmark. Credit the creator and link the original. Keep the excerpt out of the source repo. Check the intended distribution of the recording and slides that show it. |
| NASA still and derived two-track MP4 | NASA sample distributed through scikit-image and described as public domain. [Pinned source still](https://github.com/scikit-image/scikit-image/blob/v0.25.2/skimage/data/astronaut.png) · [Attribution](https://scikit-image.org/docs/0.26.x/api/skimage.data.html#skimage.data.astronaut) | Reproducible, explicitly labeled controlled verification. Two copies of one still exercise two tracks and an image-space entry, with no field-ground-truth claim. Credit NASA via scikit-image. |
| Offline test fixtures | Team Astra Fly's generated test frames and authored JSON under `backend/tests/`. | Deterministic API and rule tests only. The normal runtime uses real inference. |
| YOLO26n weights and Ultralytics ByteTrack configuration | Official `yolo26n.pt` and the `bytetrack.yaml` shipped by Ultralytics 8.4.216. Ultralytics lists AGPL-3.0 and an Enterprise option. [Weights release](https://github.com/ultralytics/assets/releases/tag/v8.4.0) · [Ultralytics licensing](https://www.ultralytics.com/license) | Installed locally. Confirm the team's distribution license and source/notice obligations before sharing the integrated app. Supply a verified download link for the checkpoint. |
| Basemap and dependency notices | The demo MapLibre style is local. Frontend and backend dependency versions are in the two lockfiles. | World features render from app GeoJSON. There are no external map tiles in the verified demo. Collect notices for the exact packages and any native binaries included in a distribution. |

Verified SHA-256 for the pinned NASA still is `88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5`. Model and tracker configuration digests and runtime versions are in the [measurement log](../docs/STATUS.md#measured-on-this-machine).

## Local aerial replay validation source

| Field | Recorded value |
| --- | --- |
| Source ID and local file | `aerial-intersection-validation` · `data/demo_video/aerial-intersection-validation.mp4` |
| Source and creator | [Aerial View of Busy Urban Intersection by Matthias Groeneveld](https://www.pexels.com/video/aerial-view-of-busy-urban-intersection-35172060/) |
| Terms and use | [Pexels License](https://www.pexels.com/license/) and [Pexels terms](https://www.pexels.com/terms-of-service/). The excerpt is retained locally for replay verification. The terms restrict standalone distribution. |
| Changes | Four-second excerpt starting near 00:12, sampled at 10 FPS, re-encoded as MP4 at 1080×1920 without audio. |
| SHA-256 | `2b08fdd659f337e7ce4898098b09c64a3f49c204854cdfb02beb623ba8ea71b7` |
| Capture time and geospatial state | Capture UTC unavailable. Aerial camera without verified calibration. |

## Controlled rule verification source

The controlled MP4 uses the public-domain NASA still from `skimage.data.astronaut`. The verification fixture pastes the 512×512 still onto a 768×512 black canvas at `x = 16 + 6 × frame_index` and `y = 0` for 38 frames at 10 FPS. The image ROI starts at x=385 and extends to the right edge. The zone rule confirms after three frames and retains the annotated confirmation thumbnail in a disposable verification database. Capture time and world location are unavailable. [NASA still attribution](https://scikit-image.org/docs/0.23.x/api/skimage.data.html#skimage.data.astronaut)

The system smoke test builds a separate two-track controlled MP4 at 1152×512 with 45 frames at 10 source FPS. A second copy of the same still is fixed at x=640. The left copy moves into the x=385–610 image ROI and stops after frame 37. The crowd threshold is one, so two accepted anonymous person tracks over three frames exercise the count rule. This footage has no capture timestamp or world calibration. The Windows encode used in Prompt 6 had SHA-256 `b7eebbac7fd455257fbf988f07be4a29a8ccd8f75d8170c9e44efbb040f925db`. [Build the controlled input](../docs/SMOKE_TEST.md#inputs)

The [README screenshots](../README.md#dashboard) show this controlled replay and its saved audit after restart. The portrait in the replay is credited to NASA via scikit-image and is shown here to document the demo. [NASA media usage guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/)

## Source provenance template

Complete one record per source before use.

| Field | Value |
| --- | --- |
| Source ID and display title | |
| Asset owner and original source or URL | |
| License or written permission and link or private reference | |
| Required attribution | |
| Permitted processing, display, evidence, and submission uses | |
| Redistribution limits for footage, thumbnails, screenshots, and recordings | |
| SHA-256 digest of the approved MP4 | |
| Capture time and provenance, if verified | |
| Fixed or moving camera and calibration reference, if verified | |
| Approved local retention and deletion date | |

## Evidence retention

`retain_thumbnails` is off by default. Enable it per source only when the source permission covers local evidence. A saved thumbnail comes from the annotated confirmation frame of an actual candidate. It is limited to 640 pixels on its longest side and 128 KiB, stored in private SQLite, and served from the incident route with `Cache-Control: no-store`. Only the latest stream frame and a bounded queue of observations are kept in memory for replay. The verification stage is temporary. Retain its database only for the authorized verification period and dispose of it afterward using the source's agreed policy.

PowerShell digest command

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\data\demo_video\approved.mp4'
```

Linux and WSL digest command

```bash
sha256sum data/demo_video/approved.mp4
```
