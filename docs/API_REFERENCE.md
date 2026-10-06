# Referencia de la API

Generada con `scripts/gen_api_doc.py` desde `/openapi.json` (no editar a mano). `*` = parametro obligatorio.
La documentacion interactiva esta en `/docs`. Guia de uso y significado de los datos: `docs/API.md`.

## (raiz)

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/` | Dashboard |  |  |

## admin

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| POST | `/api/admin/rotate` | Admin Rotate |  |  |

## attendance

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/attendance` | Attendance | `date` |  |

## attendance.csv

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/attendance.csv` | Attendance Csv | `date` |  |

## cameras

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/cameras` | Cameras |  |  |
| GET | `/api/cameras/{cam_id}` | Camera Detail | `cam_id`* |  |

## chat

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| POST | `/api/chat` | Chat | `x-session-id` | ChatRequest |
| POST | `/api/chat/feedback` | Chat Feedback |  | FeedbackRequest |
| GET | `/api/chat/history` | Chat History | `session_id`*, `limit` |  |
| POST | `/api/chat/stream` | Chat Stream | `x-session-id` | StreamRequest |

## connections

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/connections` | Connections |  |  |

## conocimiento

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/conocimiento` | Knowledge Page |  |  |

## correlation

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/correlation` | Correlation | `ts`, `event_id`, `before`, `after` |  |

## cowork

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/cowork/detail` | Cowork Detail |  |  |

## debug

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/debug/payload/{cam_id}` | Debug Payload | `cam_id`* |  |
| GET | `/api/debug/payload/{cam_id}/media` | Debug Payload Media | `cam_id`* |  |

## detections

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/detections` | Get All Detections |  |  |
| GET | `/api/detections/{cam_id}` | Get Camera Detection | `cam_id`* |  |

## devices

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/devices` | Devices |  |  |
| GET | `/api/devices/audit` | Audit | `device`, `limit` |  |
| GET | `/api/devices/{dev_id}` | Device | `dev_id`*, `refresh` |  |
| PUT | `/api/devices/{dev_id}/manage` | Set Manage | `dev_id`* |  |
| POST | `/api/devices/{dev_id}/onvif-action` | Onvif Action | `dev_id`* |  |
| GET | `/api/devices/{dev_id}/onvif/{op}` | Onvif Read | `dev_id`*, `op`* |  |
| POST | `/api/devices/{dev_id}/sunapi/action` | Sunapi Action | `dev_id`* |  |
| GET | `/api/devices/{dev_id}/sunapi/spec` | Sunapi Spec | `dev_id`*, `cgi`*, `submenu`*, `action`* |  |
| GET | `/api/devices/{dev_id}/sunapi/tree` | Sunapi Tree | `dev_id`* |  |
| GET | `/api/devices/{dev_id}/sunapi/view` | Sunapi View | `dev_id`*, `cgi`*, `submenu`*, `channel` |  |

## dispositivos

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/dispositivos` | Devices Page |  |  |

## events

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/events` | List Events | `cam_id`, `type`, `since`, `until`, `has_alert`, `limit` |  |
| GET | `/api/events/aggregate` | Events Aggregate | `hours`, `since`, `until`, `bucket` |  |
| PATCH | `/api/events/{event_id}/review` | Review Event | `event_id`* |  |

## face-sightings

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/face-sightings` | List Face Sightings | `cam_id`, `name`, `since`, `until`, `limit` |  |
| GET | `/api/face-sightings/{sighting_id}/body` | Face Sighting Body | `sighting_id`* |  |
| GET | `/api/face-sightings/{sighting_id}/image` | Face Sighting Image | `sighting_id`* |  |

## faces

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/faces` | List Faces |  |  |
| POST | `/api/faces` | Register Face |  |  |
| DELETE | `/api/faces/{face_id}` | Delete Face | `face_id`* |  |
| GET | `/api/faces/{face_id}/image` | Face Image | `face_id`* |  |

## health

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/health` | Health |  |  |

## identidades

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/identidades` | Identities Page |  |  |

## iot

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/iot/config` | Config |  |  |
| GET | `/api/iot/devices` | Devices |  |  |
| GET | `/api/iot/events` | Events | `device_id`, `limit` |  |
| GET | `/iot` | Iot Page |  |  |

## knowledge

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/knowledge` | Get Knowledge |  |  |
| PUT | `/api/knowledge` | Put Knowledge |  |  |

## occupancy

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/occupancy` | Occupancy | `date` |  |

## onvif

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/onvif/endpoints` | Endpoints |  |  |
| POST | `/api/onvif/endpoints` | Add Endpoint |  |  |
| DELETE | `/api/onvif/endpoints/{ep_id}` | Delete Endpoint | `ep_id`* |  |
| PUT | `/api/onvif/endpoints/{ep_id}/auth` | Set Auth | `ep_id`* |  |
| DELETE | `/api/onvif/endpoints/{ep_id}/auth` | Clear Auth | `ep_id`* |  |
| PUT | `/api/onvif/endpoints/{ep_id}/listen` | Set Listen | `ep_id`* |  |
| GET | `/api/onvif/endpoints/{ep_id}/live` | Live | `ep_id`*, `seconds` |  |
| POST | `/api/onvif/endpoints/{ep_id}/probe` | Probe | `ep_id`* |  |
| GET | `/api/onvif/events` | Events | `endpoint`, `limit`, `since` |  |
| GET | `/onvif` | Onvif Page |  |  |

## people

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/people` | People | `category`, `q`, `only_named`, `limit`, `scope` |  |
| POST | `/api/people/accept-suggestions` | Accept Suggestions |  | AcceptBody |
| POST | `/api/people/bulk-category` | Bulk Category |  | BulkBody |
| POST | `/api/people/consolidate` | Consolidate |  |  |
| GET | `/api/people/duplicates` | Duplicates | `min_sim`, `limit` |  |
| GET | `/api/people/overview` | Overview |  |  |
| GET | `/api/people/same-name` | Same Name |  |  |
| GET | `/api/people/today` | People Today |  |  |
| PATCH | `/api/people/{sid}/category` | Set Category | `sid`* | CategoryBody |
| GET | `/api/people/{sid}/similar` | Similar | `sid`*, `min_sim`, `limit` |  |
| GET | `/api/people/{sid}/visits` | Person Visits | `sid`*, `limit` |  |

## person-visits

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/person-visits` | List Visits | `cam_id`, `subject_id`, `since`, `until`, `limit`, `include_hidden`, `unassigned` |  |
| GET | `/api/person-visits/{vid}/body` | Visit Body | `vid`* |  |
| GET | `/api/person-visits/{vid}/face` | Visit Face | `vid`* |  |

## pets

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/pets/crops` | Pets Crops | `unlabeled`, `label`, `limit`, `order`, `pred` |  |
| GET | `/api/pets/crops/{cid}/image` | Pets Image | `cid`* |  |
| POST | `/api/pets/crops/{cid}/label` | Pets Label | `cid`* | PetLabel |
| GET | `/api/pets/model` | Pets Model |  |  |
| GET | `/api/pets/stats` | Pets Stats |  |  |
| POST | `/api/pets/suggest` | Pets Suggest |  |  |

## pipeline

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/pipeline` | Pipeline |  |  |

## releases

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/releases` | Releases |  |  |

## reports

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/reports` | List Reports | `limit` |  |
| POST | `/api/reports/generate` | Generate Report Now | `period_hours` |  |

## searxng

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/searxng/search` | Searxng Search | `q`, `format` |  |

## snapshot

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/snapshot/{cam_id}` | Snapshot | `cam_id`* |  |

## snapshots

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/snapshots` | List Snapshots | `cam_id`, `since`, `until`, `trigger`, `limit` |  |
| GET | `/api/snapshots/file/{snapshot_id}` | Serve Snapshot | `snapshot_id`* |  |
| POST | `/api/snapshots/{cam_id}` | Trigger Snapshot | `cam_id`* |  |

## spot

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/spot` | Spot Animation |  |  |

## stats

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/stats` | Stats |  |  |

## storage

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/storage/stats` | Storage Stats |  |  |

## stream

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/stream/{cam_id}` | Stream | `cam_id`* |  |

## subjects

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/subjects` | List Subjects | `since`, `limit` |  |
| GET | `/api/subjects/stats` | Subjects Stats |  |  |
| PATCH | `/api/subjects/{sid}` | Rename Subject | `sid`* |  |
| DELETE | `/api/subjects/{sid}` | Delete Subject | `sid`* |  |
| GET | `/api/subjects/{sid}/body` | Subject Body | `sid`* |  |
| GET | `/api/subjects/{sid}/face` | Subject Face | `sid`* |  |
| POST | `/api/subjects/{sid}/merge` | Merge Subject | `sid`* |  |

## system

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/system` | System Metrics |  |  |

## timeline

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/timeline` | Timeline | `since`, `until` |  |

## vehicles

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/vehicles` | Vehicles | `state`, `cam_id`, `since`, `limit` |  |
| PATCH | `/api/vehicles/{vid}` | Vehicle Patch | `vid`* | VehiclePatch |
| GET | `/api/vehicles/{vid}/image` | Vehicle Image | `vid`* |  |
| GET | `/api/vehicles/{vid}/plate` | Vehicle Plate Image | `vid`* |  |

## version

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/version` | Version |  |  |

## visits

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/visits` | List Visits | `ip`, `since`, `until`, `limit` |  |

## vlm

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/vlm` | Vlm Health |  |  |

## zonas

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/zonas` | Zones Page |  |  |

## zones

| Metodo | Ruta | Resumen | Parametros | Cuerpo |
|---|---|---|---|---|
| GET | `/api/zones` | List Zones |  |  |
| GET | `/api/zones/{cam_id}` | Get Zones | `cam_id`* |  |
| PUT | `/api/zones/{cam_id}` | Put Zones | `cam_id`* |  |
