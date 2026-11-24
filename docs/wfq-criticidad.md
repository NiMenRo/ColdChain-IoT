# WFQ por bandas de criticidad dentro de HIGH

## Motivo y estado

WFQ se aplica a las lecturas HIGH mediante dos bandas de criticidad, H8 y H9,
con pesos predeterminados 2 y 3. Este documento describe la política vigente;
la implementación y sus comprobaciones se mantienen en el código y sus pruebas.
No demuestra resultados experimentales por sí mismo.

WFQ necesita flujos que compitan por servicio. Un solo flujo se atiende como
FIFO; varios flujos con peso 1 ofrecen equidad, pero no diferenciación
ponderada. Por eso no basta con llamar WFQ a toda la cola HIGH ni con citar
el arbitraje 4:2:1 entre clases.

## Dos niveles independientes

1. **Entre clases:** ciclo persistente H,H,H,H,M,M,L, que omite colas vacías.
   Con las tres clases saturadas, HIGH obtiene cuatro de siete selecciones.
2. **Dentro de HIGH:** WFQ entre dos bandas de criticidad ya calculada por
   el backend. MEDIUM conserva RR por dispositivo/sensor; LOW conserva FIFO.

| Flujo lógico HIGH | Criticidad C | Peso por defecto |
|---|---|---:|
| H8 | 8 ≤ C < 9 | 2 |
| H9 | C = 9 | 3 |

Cada banda es un flujo lógico FIFO. Dispositivo, sensor e identidad se conservan
en cada lectura, pero no definen flujos WFQ separados. La banda se determina a
partir de la criticidad ya calculada: H8 para 8 ≤ C < 9 y H9 para C = 9. Una
lectura nueva entra en su banda al admitirse; las lecturas pendientes no se
reclasifican si cambia la criticidad de lecturas posteriores del dispositivo.

Los pesos 2:3 favorecen proporcionalmente H9 sin excluir H8. Son valores
configurables, no pesos óptimos obtenidos experimentalmente. Con ambas bandas
continuamente pendientes y coste unitario, las cuotas objetivo dentro de HIGH
son 2/5 para H8 y 3/5 para H9. Las diferencias de discretización se evalúan
sobre ventanas de selecciones; no se promete ese reparto para cualquier prefijo
pequeño, tráfico finito o bandas que se vacían.

La configuración predeterminada es
`QOS_WFQ_BAND_WEIGHTS={"H8":2,"H9":3}`. Una personalización debe declarar
exactamente ambas bandas con pesos numéricos finitos positivos.
El snapshot experimental y `/qos/runtime` identifican la política como
`criticality_bands_v1` y muestran sus pesos efectivos. La configuración anterior
`QOS_WFQ_FLOW_WEIGHTS` no se reutiliza: si contiene valores, el arranque exige
migrarla explícitamente para no aplicar silenciosamente otra semántica.

## Etiquetas y reloj virtual

La unidad de servicio es una lectura: L=1. Para la lectura k del flujo c:

```text
S(c,k) = max(F(c,k-1), V al admitir)
F(c,k) = S(c,k) + 1 / w(c)
```

Se selecciona la cabecera con menor F. En empate se usa el orden global de
admisión. El incremento es inversamente proporcional al peso: H9 acumula
etiquetas más pequeñas por lectura que H8 y obtiene más oportunidades.
No basta con ordenar directamente por criticidad: eso sería prioridad
estricta y podría dejar sin servicio indefinidamente a criticidades menores.

V corresponde a un servidor fluido GPS de capacidad una lectura por
oportunidad HIGH, no al reloj de pared. Durante una oportunidad, su pendiente
es `1 / suma(pesos de flujos GPS activos)`. Si un flujo termina en mitad de
esa oportunidad, hay que retirar su peso y seguir con la capacidad restante.
Los flujos GPS activos no son necesariamente los que aún tienen paquetes en
la cola discreta: extraer un paquete no permite olvidar su trabajo fluido.

## Pseudocódigo

```text
admitir(lectura):
    C = criticidad_calculada_por_backend
    c = H8 si 8 <= C < 9; H9 si C = 9
    F = max(ultimo_F.get(c, 0), V) + 1 / peso[c]
    ultimo_F[c] = F
    añadir a pendientes (lectura, F, orden_admision, c)

seleccionar_HIGH():
    si pendientes está vacío: devolver vacío
    (lectura, F, orden, c) = retirar el mínimo por (F, orden_admision)
    presupuesto_GPS = 1
    mientras presupuesto_GPS > 0:
        activos = {b en {H8, H9} | ultimo_F.get(b, 0) > V}
        si activos está vacío: terminar el ciclo
        W = suma(peso[b] para b en activos)
        siguiente_fin = min(ultimo_F[b] para b en activos)
        coste = (siguiente_fin - V) * W
        si coste <= presupuesto_GPS:
            V = siguiente_fin
            presupuesto_GPS -= coste
        si no:
            V += presupuesto_GPS / W
            presupuesto_GPS = 0
    devolver lectura
```

En la condición del ciclo, `c` representa cualquier banda con trabajo fluido
pendiente. Los flujos GPS activos se determinan por sus marcas de finalización,
no por la presencia de paquetes en la cola discreta; por eso una banda puede
seguir activa aunque ya no tenga lecturas pendientes. Si ambos flujos quedan
inactivos, V no avanza durante el tiempo ocioso. Una nueva admisión usa
`max(ultimo_F[c], V)`.

## Ejemplo y límites

Con seis lecturas pendientes en cada banda, todas admitidas con V=0, las
etiquetas iniciales son H8: 1/2,1,3/2… y H9: 1/3,2/3,1…. Las primeras
selecciones favorecen H9 sin eliminar las oportunidades de H8. Los empates
dependen del orden global de admisión, no del nombre de banda.

- No se garantiza equidad entre dispositivos dentro de una misma banda.
- No se mide ni reserva ancho de banda de red: se planifica atención backend.
- Coste unitario no significa que todas las lecturas consuman la misma CPU,
  tiempo SQL o tiempo de notificación. Los pesos reparten selecciones.
- Los pesos y cuotas no garantizan latencias máximas ni una mejora universal.
- Una lectura ya en atención no es interrumpida.
- La ausencia de inanición presupone que la atención progresa, pesos positivos
  y admisión válida; no garantiza aceptar tráfico cuando las colas están llenas.
- Los resultados anteriores al cambio no validan esta política.

## Evidencia de las nuevas pruebas

La política de planificación y la medición son aspectos distintos. Una tasa
de recepción MQTT no demuestra que WFQ haya reducido la latencia ni que un
correo haya llegado. Las campañas nuevas deben conservar configuración,
corpus y trazas, y comparar WITH_QOS con WITHOUT_QOS bajo condiciones
equivalentes. No se reutilizan los 14.708 registros históricos.

La captura es **opcional y explícita**: `TELEMETRY_TRACE_FILE` apunta a un
archivo JSONL diferente por proceso. Con la variable vacía no se crea archivo
ni se dispone de esta evidencia. Usar rutas absolutas dentro de `.coldchain/`,
que está ignorado por Git; no introducir credenciales ni payloads completos
en los archivos de resultados.

El productor incluye UUID de mensaje, sesión del productor, secuencia por
dispositivo y ejecución (`COLDCHAIN_RUN_ID`, cuando corresponde). La secuencia
se asigna antes de publicar, no al recibir. El backend preserva el UUID en
`sensor_readings.source_message_id`; sus lecturas tienen UUID determinista
por mensaje/sensor. Las alertas se enlazan por `reading_id`, sin cambiar el
esquema existente. Una repetición del mensaje conserva esos IDs y no vuelve
a crear las lecturas/alertas ya confirmadas.

El emisor captura intento, aceptación local, finalización `on_publish` y error.
`on_publish` significa envío a red con QoS 0, PUBACK con QoS 1 y PUBCOMP con
QoS 2; ninguno demuestra recepción por el backend. El receptor captura cada
callback y el tamaño `len(msg.payload)` antes de admitirlo. El emisor mide
los mismos bytes UTF-8 serializados una sola vez. No se incluyen cabeceras
MQTT/TCP/TLS ni se multiplican bytes por el número de sensores.

Los journals registran configuración WFQ/cuotas, admisión, rechazo, fallo,
cancelación, replay y persistencia tras confirmar el commit. El timestamp
individual de cada sensor se conserva en `reading_timestamps`; la latencia
extremo a extremo usa ese instante, no el tiempo de clasificación.
Lectura y alertas se confirman en la misma transacción: la métrica
`device_to_alert_persist_ms` acaba en ese commit, no en el envío del correo.

La conciliación es **offline y de solo lectura**:

```powershell
.\backend\.venv\Scripts\python.exe -B backend/scripts/reconcile_telemetry.py `
  --producer .coldchain/telemetry/producer.jsonl `
  --backend .coldchain/telemetry/backend.jsonl `
  --start 2026-11-20T12:00:00+00:00 `
  --end 2026-11-20T12:01:00+00:00 `
  --observed-until 2026-11-20T12:01:10+00:00 `
  --grace-seconds 10
```

Las fechas y nombres anteriores son ilustrativos: sustituir por los reales.
`--producer` y `--backend` aceptan varios archivos (incluir reinicios).
Añadir `--run-id UUID` para una ejecución; sin ese argumento se concilia
tráfico emitido sin ejecución. El worker experimental propaga la ejecución
y, si la captura está habilitada, usa un archivo emisor separado por arranque.
Los mensajes trazados de otra ejecución no se reasignan a la ejecución activa.

La cohorte contiene intentos en `[start,end)`, con finalización observada.
La recepción tiene límite `end + grace`; los callbacks posteriores se
reportan como tardíos y no reescriben retrospectivamente esa ventana.
PDR = mensajes únicos de la cohorte recibidos dentro del límite / mensajes
únicos con publicación completada. Los errores de publicación son un contador
separado, no pérdida de red. El goodput es bytes útiles de mensajes únicos
recibidos / segundos desde start hasta end+grace, en bytes/s.

Por defecto el reporte es provisional y las tasas son NULL. Solo añadir
`--confirm-complete-capture` tras recoger **todos** los archivos de los
procesos participantes, comprobar que no hubo errores de captura y cerrar
la ventana de observación. Publicaciones sin resultado conocido o recepciones
sin envío correlacionable mantienen el reporte provisional. Una secuencia
reutilizada dentro de la misma sesión o tamaños contradictorios invalidan
la evidencia en vez de corregirse silenciosamente. Un reinicio usa otra sesión.

Para comparar relojes, `TELEMETRY_CLOCK_DOMAIN` debe tener el mismo valor no
vacío en emisor y backend, **solo cuando se haya verificado su sincronización**
(por ejemplo, ejecución en el mismo host). No sincroniza ni valida relojes:
es una declaración del operador. Sin dominio comparable o con timestamps
inválidos, las latencias son NULL; deltas negativos no se convierten en cero.
La ventana temporal entre hosts también presupone relojes sincronizados.

Estos journals no sustituyen el almacenamiento durable ni garantizan captura
ante caídas del proceso/disco. No hay transacción distribuida entre SQL y
archivo: si el commit existe y falla su traza, el reporte queda incompleto.
Los errores se registran en logs y descalifican una campaña como evidencia
completa. La instrumentación añade coste de E/S que debe mantenerse comparable
entre escenarios. La interfaz histórica conserva su latencia ingesta→commit
y no incorpora automáticamente estas métricas offline ni rellena PDR legado.

### Consulta desde la aplicación

Las nuevas ejecuciones iniciadas desde Simulación pueden generar captura
gestionada por el backend (`TELEMETRY_EVIDENCE_ENABLED=true`, por defecto).
El simulador gestionado debe estar habilitado como en el entorno local habitual;
no se inventa evidencia si el productor no arranca o si se desactiva la captura.
Los archivos quedan por UUID de ejecución bajo `.coldchain/evidence`, o en
`TELEMETRY_EVIDENCE_DIR` si se configura otra raíz local. No se cargan aquí
los archivos de campañas anteriores ni se reconstruyen envíos históricos.

- **Simulación:** muestra enviados/recibidos únicos, lecturas guardadas,
  latencias media/p95 y estado de captura; el enlace abre su ejecución en QoS.
- **QoS / Analytics:** compara las ejecuciones elegidas, muestra duplicados,
  pendientes/no recibidos en la ventana, PDR, bytes útiles y bytes/s, latencias
  por clase, cuotas/pesos y procedencia/ventanas.
- La consulta usa `GET /experiment-runs/{UUID}/evidence`, con la autenticación
  existente. El cliente no manda rutas, no consulta SQL y no calcula PDR.
- Los datos provisionales se refrescan cada ocho segundos sin solicitudes
  superpuestas; no se aceptan respuestas de otra selección o tras desmontar.

Al finalizar, el productor recibe una señal cooperativa, termina publicaciones
pendientes y confirma el cierre de su journal. El backend conserva una gracia
de recepción fija (`TELEMETRY_EVIDENCE_GRACE_S=2`, configurable) antes de cerrar
admisión y drenar. Solo después de confirmar captura y ventana se publican tasas
finales. Un cierre forzado, un reinicio incompleto, un journal corrupto o errores
de captura dejan resultados incompletos/«No disponible», no éxito supuesto.

El límite de recepción define PDR y goodput, pero no corta las latencias de
lecturas recibidas a tiempo que terminan de persistirse durante el drenaje.
La pantalla identifica también hasta cuándo se observó esa persistencia.
Las clases de evaluación de WITHOUT_QOS se derivan al consultar los valores
guardados, según la matriz vigente; no se crean clasificaciones en su pipeline
ni en SQL. Las métricas históricas de ingesta se muestran con su nombre propio.

La API limita la lectura conjunta a 64 MiB por captura y falla de forma explícita
en vez de mostrar un subconjunto como completo. Conservar el directorio de
evidencia es necesario para consultar ejecuciones después de reiniciar o
desplegar; esta captura local no es almacenamiento distribuido ni una garantía
durable frente a pérdida del disco.

### Campaña real reproducible

El arnés `backend/scripts/validate_telemetry_campaign.py` crea PostgreSQL y
Mosquitto desechables en puertos aleatorios de loopback. PostgreSQL usa tmpfs,
no el volumen del proyecto. Ejecuta Alembic únicamente en esa base nueva,
usa credenciales efímeras y monta los certificados locales en solo lectura,
sin desactivar la verificación TLS. Al terminar detiene y elimina solo sus
propios contenedores, conservando journals, corpus, resultados SQL y logs.
No carga `.env` ni habilita notificaciones.

```powershell
.\backend\.venv\Scripts\python.exe -B backend/scripts/validate_telemetry_campaign.py `
  --execute --output .coldchain/telemetry-campaign-NUEVA
```

El directorio de salida debe ser nuevo: se rechaza sobrescribir evidencia.
El protocolo contiene dos calentamientos excluidos, dos cargas (10 mensajes/s
y ráfaga), tres repeticiones por escenario y orden de escenarios alternado.
El productor es otro proceso que usa DevicePublisher/MQTTClient reales con
mediciones sintéticas predefinidas, no sensores físicos. Los servicios y
commits son reales; no es una validación de HTTP, interfaz o correo.

Dos casos adicionales precargan H8 y H9 antes de liberar la atención para
comprobar reparto 2:3 bajo competencia. La espera impuesta se identifica
expresamente; sus latencias no se mezclan con la comparación en tiempo real.
La matriz actual produce C=3,6,8,9 para payloads válidos; los casos con C=8 y
C=9 comprueban respectivamente H8 y H9 en la campaña.

Los diagnósticos separados generan ausencia de suscripción, republicaciones
con la misma identidad y un reinicio real del proceso productor. La pérdida
por falta de suscripción es intencional y de aplicación, no pérdida IP.
Las republicaciones son duplicados inyectados, no evidencia de retransmisión
espontánea del protocolo MQTT.

`backend/scripts/summarize_telemetry_campaign.py DIRECTORIO` analiza el resultado
de solo lectura y muestra latencia por clase/criticidad. Las etiquetas de
evaluación se calculan offline desde el corpus guardado, también para
WITHOUT_QOS: no se crean clasificaciones en su procesamiento ni en SQL.
El resumen conserva versiones y hashes de código. Tres repeticiones locales
no establecen significancia estadística ni una mejora universal de QoS.

### Resultado de la campaña ejecutada

Artefactos: `.coldchain/telemetry-campaign-20261120-02/`.
`campaign.json` contiene resultados y configuración; `summary.json`, el
análisis por clase; cada subdirectorio conserva corpus, journals, selección,
conciliación y filas SQL exportadas. `cleanup.json` confirma la eliminación
de los dos contenedores de prueba. Los servicios originales de los puertos
5433 y 8883 permanecieron activos.

Se completaron **19 casos**: dos calentamientos excluidos, 12 comparaciones,
dos backlogs y tres diagnósticos. Alembic alcanzó `c5e7a9d1f203` sobre
PostgreSQL real aislado; MQTT usó autenticación y TLS con verificación.

En las 12 comparaciones se observaron 1.080 mensajes únicos enviados y
1.080 recibidos, 3.240 lecturas y 1.890 alertas persistidas, sin rechazos
ni fallos de atención. PDR=100% y pérdida=0% son resultados de esta carga
local, conciliados desde ambos extremos, no una garantía ni una constante.
Los payloads completos de esas comparaciones midieron **561–564 bytes**.

Latencia media generación→commit, en milisegundos; media de las tres medias
por ejecución, con el mismo corpus y etiquetas de evaluación offline:

| Carga | Clase | WITH_QOS | WITHOUT_QOS |
|---|---|---:|---:|
| 10 mensajes/s | Alta | 198,2 | 196,5 |
| 10 mensajes/s | Media | 165,6 | 188,9 |
| 10 mensajes/s | Baja | 236,0 | 206,3 |
| Ráfaga | Alta | 2.735,6 | 2.953,3 |
| Ráfaga | Media | 2.193,7 | 2.886,2 |
| Ráfaga | Baja | 5.052,5 | 2.892,7 |

En ráfaga la priorización redujo la media de alta y media a costa de baja;
con 10 mensajes/s no mejoró la media de alta. No hay mejora universal.
La distribución y el coste de clasificar/registrar métricas forman parte
del experimento; estas diferencias no aíslan por sí solas causalidad de WFQ.

En el backlog WITH_QOS había 100 lecturas H8 y 100 H9 antes de liberar la
atención. Las primeras 100 selecciones fueron **40 H8 y 60 H9**, conforme a
pesos 2:3. WITHOUT_QOS conservó FIFO. No se presenta este caso precargado
como una comparación de latencia operativa.

Diagnósticos separados:
- Sin suscripción: 8 publicaciones completadas y 0 recepciones; **PDR=0%**,
  pérdida de aplicación=100%, sin lecturas/alertas persistidas.
- Duplicados: 8 identidades únicas y 8 recepciones adicionales; solo
  **24 lecturas y 14 alertas**, sin duplicar efectos persistentes.
- Reinicio: dos procesos productores, 16 identidades únicas recibidas y
  **48 lecturas**; las secuencias reiniciadas no se confundieron entre sesiones.

Sin calentamientos, el conjunto completo contiene 1.512 envíos únicos,
1.504 recepciones únicas, 3.712 lecturas y 2.332 alertas. No combinar su tasa
global con la comparación nominal: incluye la pérdida inducida expresamente.
