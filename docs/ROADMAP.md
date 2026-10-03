# Roadmap

Estado a 2026-10-02 (v2.3.0). Cada línea indica qué falta y cómo sabremos que terminó.

## 1. Videoportero (timbre)
**Equipo:** panel exterior Dahua VTO y dos monitores interiores VTH. Expone HTTP con autenticación Digest, RTSP y el puerto propietario 37777.
**Plan:**
- Crear en el VTO un usuario dedicado de solo lectura; guardar su clave solo en el `.env` del servidor.
- Escuchar los eventos del equipo por `eventManager.cgi?action=attach` (llamada, llamada sin respuesta, apertura de puerta) y tomar una captura con `snapshot.cgi` en cada timbre.
- Tabla `doorbell_events` con hora, captura, resultado del reconocimiento facial del visitante y, si hubo, a quién llamó; aviso al dashboard y a Wazuh.
- Enlazar el timbre con las cámaras de la entrada (Escaleras de entrada y Exteriores) para recuperar los segundos previos del *pre-roll*.
**Hecho cuando:** un timbre real aparece en la línea de tiempo con su captura en menos de 5 s, y el visitante entra a la base "por revisar" si no se reconoce.

## 2. Personas: empleados, invitados y asistencia
**Hecho:** categorías `revisar` / `empleado` / `invitado`, modal de clasificación, parecidos y fusión, `/api/attendance` (+ CSV), retención por categoría.
**Falta:**
- Consolidación automática de sujetos duplicados. Hoy hay 2 pares de 70 % o más y 31 entre 55 y 70 %; la regla actual solo compara cada visita nueva contra el promedio de cada sujeto, nunca los sujetos entre sí.
- Reporte de asistencia con interfaz propia y reglas: entrada = primera detección en cámaras interiores; salida = última; tolerancia de huecos; fines de semana y festivos; envío programado.
- Alta de empleados con foto de referencia para no depender del azar de la primera detección.
- Invitados: solo cantidades y capturas, nunca reporte individual de asistencia.
**Hecho cuando:** el reporte del día coincide con la asistencia real de una semana de prueba, con menos de 1 persona mal clasificada.

## 3. Mascotas (Akamaru, Mojo-jojo y Gigi)
**Hecho:** recolector de recortes, página de etiquetado y "Entrenar y sugerir" (clasificador sobre características de ImageNet con validación cruzada).
**Falta:** reunir unas 60 etiquetas, hacer el ajuste fino real, y usar el modelo en vivo para que `animal` solo alerte con perros desconocidos.
**Hecho cuando:** 90 % de acierto en validación y cero alertas de `animal` por las tres mascotas durante una semana.

## 4. Vehículos
**Hecho:** registro de vehículos estacionados en Exterior 1 y 2 con llegada, permanencia y placa manual.
**Falta:** lectura automática de placas. Solo es viable en 1 o 2 lugares cercanos de la cámara de 5 MP y sobre el cuadro nativo (las capturas guardadas están reducidas); requiere un detector de placas y OCR con votación entre cuadros. Evaluar antes si se justifica.

## 5. Visión
- Comparar YOLOv8s contra YOLO26 con TensorRT en capturas reales; cambiar solo si gana.
- Dibujar cajas sobre las detecciones únicamente cuando hay una activa (panel en vivo y capturas), con interruptor por cámara.
- ReID de cuerpo y mapa de cámaras para enlazar personas sin rostro, empezando en modo observación.

## 6. Reportes y asistente
- Entrenar con SkillOpt el skill de reportes en periodos ocupados (hoy ninguna ronda superó al skill original) y construir el benchmark del chat.
- Darle al Vision Agent herramientas para consultar la base bajo demanda.

## 7. Plataforma
- Mover Umami a Coolify (respaldo hecho, pendiente de restaurar).
- Proteger `main`, exigir PR y CI, y publicar cada versión con su tag y su GitHub Release usando las notas de `app/release_notes.json`.

## Pendientes registrados el 2026-10-03

- **Zonas por cámara** (`/zonas`): ignorar (falsos positivos fijos, como la palmera de Escaleras entrada), estacionamiento con placa (solo Exterior 1 y 2) y descripción fija para el VLM; aprendizaje de los descartes de mascotas; overlay del recuadro de YOLO en las alertas para depuración automática.
- **Videoportero Dahua y sensor de puerta** (issue aparte; falta usuario de solo lectura en el VTO).
- **Ollama:** usar la GPU (`OLLAMA_LLM_LIBRARY=cuda_v13`), con aviso a NormaAI; retirar `gemma3:12b` y `qwen2.5:3b` si siguen sin uso.
- **Seguridad del host:** inventario de CVE antes de decidir JetPack 7.2.1 (`docs/JETPACK-7.2.1.md`).
- **Gobierno:** épica en Jira, espacio de Confluence y registro de riesgos de biometría (`docs/COBIT-JIRA.md`).
- Búsqueda semántica (e5) como segunda fase, solo para consultas conceptuales.
