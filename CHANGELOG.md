# Changelog

Generado desde `app/release_notes.json` (la misma fuente que muestra el dashboard). Versionado semántico: mayor = cambia el modelo de datos o el flujo; menor = funciones nuevas; parche = correcciones.

## v2.6.0 — Gestión de dispositivos y placas (2026-10-03)

Cada marca de cámara se puede consultar y administrar desde el dashboard (Hanwha por SUNAPI, Dahua y cualquier equipo ONVIF por ONVIF), siempre en solo lectura por defecto, con confirmaciones y bitácora. Los vehículos estacionados dentro de las zonas ahora se leen solos (placa).

- **Dispositivos · Gestión de dispositivos (/dispositivos)**: Lista todos los equipos con marca, modelo y firmware, y para cada uno ofrece Resumen, Gestión y Auditoría. Hanwha: el árbol completo de funciones que publica la propia cámara (sistema, red, seguridad, video, imagen, eventos, grabación…), con lectura de cada una y formularios de modificación generados desde los tipos declarados por el equipo (listas, rangos, sí/no). Dahua y otros ONVIF: red, DNS, NTP, nombre, perfiles de video, puertas y relés, con acciones (NTP, perfil de video, reiniciar, abrir puerta).
- **Dispositivos · Seguridad de la gestión**: Todo equipo arranca en solo lectura; para modificar hay que activar el modo gestión del equipo. Las acciones sensibles (red, usuarios, reinicio, perfiles de video que Thor consume, abrir puerta) piden escribir el id del equipo; restaurar de fábrica, actualizar firmware, copias de configuración y certificados nunca se permiten desde aquí. Los valores se validan contra los tipos del propio equipo y toda acción queda en una bitácora con los secretos enmascarados.
- **Dispositivos · Inventario de firmware**: El resumen muestra modelo, firmware y hora de cada equipo y avisa cuando el firmware es antiguo: hoy 8 de las 10 cámaras son LND-6010R con firmware de 2020.
- **Vehículos · Placas de vehículos estacionados**: Dentro de las zonas de estacionamiento, cada vehículo registrado se lee una vez por minuto (hasta 20 lecturas) sobre el recorte nativo y se vota entre lecturas; lo escrito a mano siempre manda. Se guarda el texto, la confianza, el origen (auto o manual) y el recorte de la placa, y la placa aparece en las alertas del vehículo. El lector (fast-alpr) se instala en el volumen de datos con scripts/install_alpr.sh, sin tocar la imagen.

Correcciones:
- El escucha ONVIF del videoportero se caía tras 8 segundos sin eventos; ahora espera más que la consulta del equipo.
- El videoportero ya no aparece duplicado como cámara Hanwha en la gestión de dispositivos.

Notas:
- Probado en vivo solo en lectura; las modificaciones están cubiertas por pruebas y por la política, pero no se aplicó ninguna a un equipo real.
- Pendiente: probar placas con un auto estacionado dentro de la zona (a 43 px de ancho la lectura de un auto lejano de noche sale con baja confianza).
- Pendiente: el control de puertas del videoportero respondió con un error al listar puertas; hay que revisar el servicio en el equipo.

## v2.5.0 — Zonas, ONVIF y videoportero (2026-10-03)

Las zonas por cámara se dibujan desde el dashboard, hay un operador ONVIF para las cámaras y el videoportero, el videoportero entra al dashboard como cámara de solo rostros, los vehículos estacionados generan alertas y el reporte usa el skill optimizado.

- **Zonas · Zonas por cámara (/zonas)**: Se dibujan polígonos sobre la imagen de cada cámara con cuatro tipos: ignorar objetos (falsos positivos fijos como una palmera), ignorar todo, estacionamiento (solo se registran vehículos dentro) y descripción fija para el VLM. Se guardan en data/zones.json y se aplican en segundos, sin reiniciar.
- **Vehículos · Alertas de vehículos estacionados**: Cada vehículo estacionado dentro de una zona de estacionamiento genera una alerta al llegar, otra cada hora mientras siga ahí (con el tiempo acumulado) y otra al irse. Son eventos con alerta del tipo vehiculo_detenido y metadato del vehículo (id, clase, duración, placa si se capturó), así que salen en la línea de tiempo, el chat y los reportes.
- **ONVIF · Operador ONVIF (/onvif)**: Lista las cámaras y equipos agregados (videoportero), sondea modelo, firmware, hora, perfiles de video con su URI de stream, servicios y usuarios, y escucha eventos de forma continua (timbre, puerta, movimiento) guardándolos por 90 días. El usuario ONVIF de cada equipo solo se guarda si el equipo lo acepta y nunca sale por la API.
- **Videoportero · Videoportero como cámara de solo rostros**: El Dahua VTO entra al dashboard como cam-vto (1920x1080, 30 fps, decodificación por hardware) con detección de rostros únicamente: sin detección de objetos, VLM ni movimiento nativo. cameras.yml no lleva claves: apunta a onvif://vto/<perfil> y la clave se resuelve del operador ONVIF, así que la rotación aplica sola.
- **Reportes · Skill de reportes optimizado (v2)**: El reporte usa el skill de la ronda 2 de SkillOpt: acierto 0.89 contra 0.59 del original en 22 casos no vistos, con reportes más cortos y completos.
- **Dashboard · Resumen del pipeline en Conexiones**: El resumen de llamadas a Qwen pasó a la ventana de Conexiones a las cámaras y se quitaron los textos sobre credenciales.

Correcciones:
- El chat clásico del dock se retiró (usaba una ventana fija de 6 h y no la búsqueda por descripción).
- Las coincidencias de la búsqueda del Vision Agent enlazan a la captura real del evento cuando existe.

Notas:
- Pendiente: mapear los eventos del timbre y la puerta del videoportero y guardar las llamadas con captura.
- Pendiente: lectura de placas solo para vehículos estacionados dentro de las zonas dibujadas (prueba de factibilidad hecha; falta un auto en la zona para validar).
- Pendiente: gestión remota de cámaras por ONVIF (hora, red, perfiles de video, reinicio) con confirmación y bitácora.
- Descartado: el conteo de personas de Hanwha (WiseAI objectcounting) no existe en las cámaras probadas (404).

## v2.4.0 — Identidades, búsqueda y calidad (2026-10-03)

La gestión de personas pasa a una página propia (/identidades) con bandeja por revisar, empleados, invitados, ocupación, asistencia y duplicados. El Vision Agent ahora encuentra eventos por su descripción, y el repositorio gana pruebas y reglas automáticas que evitan que vuelvan los fallos que ya tuvimos.

- **Personas · Página propia: Identidades**: Reemplaza los modales mezclados por una página /identidades con pestañas: Por revisar, Empleados, Invitados, Ocupación, Asistencia y Duplicados. Cada persona se clasifica con un clic o en lote, se nombra con ✎ y muestra sus parecidos con el botón 'Es la misma'. El resumen del día (empleados presentes, invitados, por revisar) queda arriba.
- **Personas · Mismos nombres se unifican**: Las identidades con el mismo nombre se fusionan en una sola (conserva la categoría más fuerte y el historial) con un botón en Duplicados. La asistencia agrupa por nombre.
- **Personas · Cámaras exteriores sin ruido**: Exterior 1 y 2 siguen reconociendo a quien ya está registrado, pero no crean identidades nuevas ni cuentan en la asistencia; su actividad queda como alertas. El Garage frontal (acceso peatonal) sí cuenta para llegada y salida.
- **Ocupación · Pestaña de ocupación**: Personas ahora en cámara, empleados presentes con minutos promedio, pico del día y personas distintas por hora (empleados, invitados, por revisar). Solo cámaras interiores y Garage frontal; ignora visitas de pocos segundos sin identidad.
- **Vision Agent · Búsqueda por descripción**: Un índice de texto (FTS5, dentro de la misma events.db) permite preguntar 'persona con bolsa naranja' o 'perro con correa en Exterior 1' y obtener las capturas con cámara y hora. En una prueba de 24 preguntas la búsqueda por palabras acertó más (0.80 de precisión en los 5 primeros) que los embeddings multilingües (0.62).
- **Datos · Retención de capturas a 90 días**: Las capturas de rostro y cuerpo se borran a los 90 días en todas las categorías (CAPTURE_TTL_DAYS); el registro y la asistencia de los empleados se conservan.
- **Calidad · Pruebas y reglas automáticas en el CI**: 28 pruebas de contrato sobre lo que ya falló en producción, un tope que impide agregar excepciones genéricas o silenciosas (la deuda actual está fijada y solo puede bajar) y reglas ast-grep contra llamadas HTTP sin timeout y consumidores de frames sin tope.
- **Versiones · Versión sincronizada con git**: La versión que muestra el dashboard se toma de la primera entrada de release_notes.json; un chequeo del CI exige que el CHANGELOG esté regenerado y, al publicar un tag vX.Y.Z, que coincida con la versión y crea el GitHub Release con estas notas. El dashboard muestra además el commit desplegado.

Correcciones:
- La limpieza por antigüedad de face_sightings tenía las comillas mal en 'Desconocido' y 'Sin rostro' y podía fallar la rotación.
- La ocupación 'ahora' contaba visitas que quedaron abiertas tras reiniciar; ahora solo cuenta lo visto en los últimos 2 minutos.

Notas:
- Pendiente: zonas por cámara (ignorar, estacionamiento con placa, descripción fija) y aprendizaje de los descartes de mascotas.
- Pendiente: videoportero Dahua y sensor de puerta (issue aparte).
- Pendiente de decisión: Ollama usa la CPU por una variable del servicio (cuda_jetpack6 en lugar de cuda_v13); afecta a NormaAI.

## v2.3.0 — Personas: empleados e invitados (2026-10-02)

Las personas detectadas se reparten en tres bases (por revisar, empleados de OXM e invitados), con búsqueda de parecidos y la base del reporte de asistencia. Las mascotas ya tienen nombre y el sistema aprende a reconocerlas.

- **Personas · Tres bases: por revisar, empleados e invitados**: Toda persona nueva queda automáticamente 'por revisar'. Desde el modal de clasificación se deriva a Empleado u Invitado con un clic, o se regresa a revisión. Las personas que ya tienen nombre aparecen con la sugerencia 'Empleado'. Las categorías aplican a todas las cámaras.
- **Personas · Parecidos y fusión**: Cada persona muestra quiénes se le parecen, con porcentaje y botón 'Es la misma', y hay una vista de pares dudosos. Se encontraron 2 pares de 70 % o más y 31 entre 55 y 70 %: sujetos existentes que el sistema nunca volvió a comparar entre sí.
- **Asistencia · Base del reporte de asistencia**: /api/attendance y /api/attendance.csv calculan por día, solo para empleados y con las cámaras interiores, la primera y última vez que se vio a cada uno, los minutos en la oficina (huecos menores a 10 minutos cuentan como presencia) y las cámaras. A los invitados solo se les reportan cantidades y capturas.
- **Datos · Retención por categoría**: Los empleados no caducan. Los invitados se conservan 90 días (GUEST_TTL_DAYS) y las personas por revisar sin nombre 30 días. El recorte automático por tope de visitas ya no borra empleados ni invitados.
- **Mascotas · Akamaru, Mojo-jojo y Gigi**: Las tres mascotas tienen nombre propio en el etiquetado y en las reglas de escena (Akamaru es el shiba café, Mojo-jojo el perro negro pequeño y Gigi el shar pei, más grande que Akamaru).
- **Mascotas · Entrenar y sugerir**: Con las etiquetas puestas, el botón 'Entrenar y sugerir' entrena un clasificador sobre las características de una red ImageNet, mide su acierto con validación cruzada y propone etiqueta para el resto de los recortes, para que solo se confirme. El ajuste fino completo llega con unas 60 etiquetas.

Notas:
- Videoportero: identificado como Dahua VTO (el panel exterior y dos monitores VTH interiores). La captura del timbre queda pendiente de credenciales de un usuario dedicado en el equipo.
- Pendiente: consolidación automática de sujetos duplicados y el reporte de asistencia con interfaz propia.

## v2.2.0 — Vision Agent, vehículos y mascotas (2026-10-02)

El asistente pasa a ser Vision Agent completo (Morphic en español sobre tus cámaras), YOLO reconoce objetos y se estrenan el registro de vehículos estacionados y el etiquetado de mascotas.

- **Vision Agent · Asistente completo sobre tus datos**: El botón del chat abre Morphic auto-hospedado, en español, con fuentes citadas, capturas, preguntas relacionadas e historial. No busca en la web: consulta alertas, personas, capturas y vehículos de THOR. Los botones de ejemplo (Alertas, Personas, Cámaras, Capturas, Reportes) son preguntas que el sistema sabe responder.
- **Visión · YOLO reconoce objetos, no solo personas**: En la misma pasada detecta autos, motos, camiones, autobuses, bicicletas, perros, gatos, mochilas, bolsos y maletas, sin costo extra medible. Las cajas quedan guardadas y se le dan al VLM como pista para describir mejor la escena. Se apaga con YOLO_OBJECTS_ENABLED=false.
- **Alertas · Menos falsas 'persona en el suelo'**: Una captura reveló que el VLM inventaba personas caídas en una oficina vacía. Ahora la alerta solo pasa si YOLO ve una persona con forma horizontal; si no, se descarta y queda la descripción.
- **Vehículos · Registro de vehículos estacionados**: En Exterior 1 y 2, todo vehículo quieto más de 3 minutos queda registrado con miniatura, hora de llegada, permanencia y estado (estacionado o se fue). La placa se puede capturar a mano; la lectura automática no está incluida porque solo es viable en los 1 o 2 lugares más cercanos de la cámara de 5 MP.
- **Mascotas · Etiquetado de las tres mascotas**: El sistema recolecta recortes de perros y gatos y ofrece una página para etiquetarlos (negro, shiba, pug, otro). Con unas 15 etiquetas por mascota se podrá entrenar el reconocimiento, para que la alerta de animal solo salte con perros desconocidos.
- **Línea de tiempo · Curvas dinámicas**: El carril General dibuja áreas apiladas suaves por tipo de alerta, con el tramo en curso punteado, burbuja con el valor al pasar el mouse y animación al cargar.
- **Reportes · Reportes completos**: El tope de 900 tokens cortaba los reportes de periodos con muchas alertas y se perdían las secciones 3 y 4. Subió a 1,600 tokens con 120 s de espera.
- **Plataforma · Versión y notas de release**: La versión actual aparece en la barra inferior; al pulsarla se abre este historial con lo que trae cada release.

Correcciones:
- El entrenamiento de prompts ya no puntúa como cero una falla del gateway: reintenta con espera y se detiene.
- La cola de entrenamiento comprueba que el gateway y el cupo de Claude respondan antes de empezar.

Notas:
- Pendiente: lectura automática de placas, reconocimiento de mascotas por nombre, y dibujar cajas sobre las detecciones solo cuando existan.

## v2.1.0 — Reglas por cámara y asistente con memoria (2026-10-01)

Cada cámara tiene su propio horario y criterio de alerta, los reportes y el chat usan cifras exactas de la base y aparece la línea de tiempo de alertas.

- **Cámaras · Vista de conexiones**: El botón de conexiones muestra por cámara la IP, el puerto y la ruta RTSP (sin credenciales), el decodificador usado, la resolución nativa, el estado, los fps y el estado de SUNAPI (movimiento y snapshots).
- **Cámaras · Rótulo, fecha y hora en la imagen**: Las 10 cámaras muestran su nombre real, fecha y hora grabados en el video. La hora sincroniza por NTP.
- **Reglas · Horarios y criterios por cámara**: Sala de Juntas alerta solo de 00:00 a 06:00 entre semana y no los fines de semana; Cocina de 00:00 a 07:00; Escaleras de entrada vigila merodeo y actividad en fin de semana; Acceso Site alerta con cualquier persona. En exteriores un auto solo alerta si lo fuerzan, no por recargarse en él.
- **Reglas · Personas y mascotas conocidas**: En cocina y garages las personas con nombre reconocido por rostro no generan alerta nocturna ni de acceso, y las tres mascotas de la casa no generan alerta de animal.
- **Alertas · Uso de teléfono en exteriores**: Nueva alerta cuando alguien mira o usa su teléfono afuera, aunque a lo lejos solo se vea una luz en la mano.
- **Reportes y chat · Hechos exactos del periodo**: Los conteos por cámara, tipo de alerta, personas y visitas se calculan en la base, con comparación contra el periodo anterior, y el modelo solo redacta. Ya no se cortan en 200 alertas ni se inventan cifras.
- **Chat · Memoria por sesión y capturas**: El chat recuerda la conversación, entiende 'esas alertas', adjunta las capturas de las alertas con las personas conocidas presentes y acepta rangos escritos como 'entre 21:00 y 22:00'.
- **Modelos · DeepSeek para chat y reportes**: El chat y los reportes usan DeepSeek con su propia llave del gateway; el análisis de cámaras sigue con Qwen.
- **Vision Agent · Chat en streaming con evidencia**: Respuesta que aparece mientras se genera, con proceso consultado, evidencia citada [E#], capturas, preguntas relacionadas y calificación 👍/👎.
- **Línea de tiempo · Alertas por cámara**: Carril general y un carril por cámara con zoom +/−, desplazamiento con las flechas y selección de un rango para preguntarle al asistente.
- **Interfaz · Chat flotante, íconos y accesibilidad**: El chat es un botón flotante desplegable; los íconos son SVG, hay foco visible, se respeta 'reducir movimiento' y Esc cierra los modales. Se agrega una animación que explica el pipeline.
- **Plataforma · Repositorio y CI**: El código se sincroniza con GitHub con revisión por PR, escaneo de secretos y chequeo estático, y las variables NEMOTRON_* pasan a VLM_* conservando las anteriores.

Correcciones:
- cam-191 volvía a FFmpeg por software tras una caída y no regresaba a NVDEC: ahora reintenta.
- La detección de caras del flujo en vivo fallaba en silencio por un nombre sin definir (face_yaw).
- La alerta 'fuera de horario' se disparaba de día.

## v2.0.0 — Personas, escenas y movimiento nativo (2026-09-30)

El sistema deja de analizar a ciegas: usa el movimiento de la propia cámara, entiende cada escena y sigue a las personas con identidad entre visitas.

- **Cámaras · Movimiento nativo por SUNAPI**: El detector de movimiento de las cámaras Hanwha disparó el análisis en las 10 cámaras. El 67 % de las llamadas al modelo eran latidos sin actividad; ahora el latido es cada 15 minutos.
- **VLM · Prompt y alertas por cámara**: config/scenes.yml define dónde está cada cámara, qué importa, qué ignorar y qué alertas permite. El resultado se valida y se sanea, y no se llama al modelo si YOLO no vio una persona.
- **Personas · Visitas e identidades**: Cada persona seguida en una cámara es una visita con su mejor rostro y cuerpo. Los rostros se agrupan en sujetos 'Persona #N' que se pueden renombrar, fusionar o borrar, con modal de Personas e identidades.
- **Captura · Pre-roll y análisis retroactivo**: Se guardan 6 segundos de cuadros a resolución nativa por cámara; al detectar a alguien se reanalizan los cuadros anteriores para recuperar el momento real de llegada.
- **Rostros · Caza de rostros**: Mientras una persona no tiene buen rostro, YOLO sube a 4 fps y se piden snapshots completos a la cámara, filtrando por nitidez y pose.
- **Descripciones · Descripciones siempre descriptivas**: Se acabó el 'Sin actividad relevante': cada evento describe la escena aunque no haya alerta, y el VLM recibe un recorte ampliado de las personas.
- **Datos · Retención de datos biométricos**: Los datos de personas sin nombre caducan a los 30 días; los nombrados se conservan.
- **Dashboard · Indicadores y medidores**: Cada tarjeta muestra movimiento, YOLO y última consulta al VLM. El medidor de GPU usa nvidia-smi y el de CPU el uso real.

Correcciones:
- El VLM fallaba 9 % de las veces por exceder el contexto: el video se reescala a 640x360.

Notas:
- Nemotron se renombra a VLM en el código; los tipos guardados en la base se conservan.

## v1.2.0 — Captura por hardware y rostros (2026-09-15)

La decodificación pasa al hardware del Jetson y el sistema empieza a recordar rostros y a clasificar alertas.

- **Captura · GStreamer con NVDEC**: La decodificación de video pasó de FFmpeg por software a hardware: el CPU del contenedor bajó de 434 % a 47 %.
- **Captura · Resolución nativa**: Las 10 cámaras se procesan a su resolución real; cam-113 recibe su formato vertical.
- **Rostros · Miniaturas e historial**: Los rostros detectados se guardan como miniatura y hay un historial consultable.
- **Alertas · Triage 👍/👎 y reportes**: Cada alerta se puede marcar importante o ruido, y un reporte generado por IA resume el periodo usando ese criterio.
- **Observabilidad · Consumo de IA en Grafana**: El dashboard separa errores del gateway por código y muestra latencias.

Correcciones:
- Los fps reportados eran ráfagas y no la tasa real; ahora se calculan en una ventana.
- Rostros falsos (cuadros y reflejos): se exige confianza del detector y una persona de YOLO debajo.
- El video enviado al VLM se limita a 10 cuadros.

## v1.1.0 — Dashboard operativo (2026-09-11)

El dashboard gana configuración, histórico y chat con memoria del pasado.

- **Dashboard · Rediseño y panel de configuración**: Nuevo diseño verde NVIDIA, histórico con filtros por rango y cámara, grid movible y línea de eventos al fondo.
- **Chat · Chat con histórico real**: La ventana de tiempo se infiere de la pregunta; hasta 12 horas se lista evento por evento y más allá se resume.
- **Cámaras · Nombres y zonas reales**: Las cámaras tienen nombre y zona, y Cowork suma un pipeline de detalle de pantallas.
- **Auditoría · Quién consulta el sitio**: Cada acceso al dashboard queda registrado con IP y navegador, además de la analítica con Umami.
- **Modelos · Gateway LLM**: El análisis pasa por un gateway con reintentos ante fallas transitorias.

## v1.0.0 — Lanzamiento inicial (2026-06-05)

Primera versión publicada de THOR Vision.

- **Captura · RTSP multicámara**: Un hilo por cámara, con buffer circular en memoria.
- **Análisis · Escena con modelo multimodal**: El modelo solo se consulta cuando hay movimiento.
- **Dashboard · Cuadrícula en vivo y chat**: Estado de las cámaras, snapshots y preguntas en lenguaje natural.
- **Datos · Persistencia y retención**: Eventos y snapshots en SQLite y disco, con borrado automático.

Notas:
- Autor del lanzamiento inicial: Diego Reyes.
