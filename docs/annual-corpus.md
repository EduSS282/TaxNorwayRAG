# Corpus por año y velocidad del build

## Qué cambia

El crawler puede adquirir versiones anuales oficiales sin inventar su vigencia. `--year 2025
--year 2026` expande únicamente las opciones anunciadas en el selector de una página de tarifas.
Al recibir cada versión, comprueba que el HTML selecciona ese mismo año. El parser vuelve a
comprobarlo al construir el corpus, incluso para capturas antiguas.

Las páginas generales siguen con `tax_year: null`. Ni la fecha de descarga ni una mención suelta
a 2026 demuestran que toda la página sea aplicable a ese año. Los años no anunciados se omiten;
un selector incompatible o ausente en una URL anual produce un fallo explícito.

## Empezar con una fuente pequeña (PowerShell, raíz del repositorio)

Con Qdrant y Ollama preparados en el portátil, no necesitas encender el LLM para indexar:

```powershell
uv run taxguide crawl `
  "https://www.skatteetaten.no/en/rates/minimum-standard-deduction/" `
  --source skatteetaten-rates-en `
  --year 2025 --year 2026 --no-follow --max-pages 3

uv run taxguide corpus build --url-prefix "/en/rates/" --language en --dry-run
uv run taxguide corpus build --url-prefix "/en/rates/" --language en --index

uv run taxguide retrieve "minimum standard deduction upper limit" `
  --mode sparse --tax-year 2025 --limit 5 --json
uv run taxguide retrieve "minimum standard deduction upper limit" `
  --mode sparse --tax-year 2026 --limit 5 --json
```

Esperado: una captura general sin año y dos anuales, si ambos años siguen publicados.
El resumen del build muestra `documents_by_tax_year` y los tiempos por etapa. `--dry-run` no
lee HTML: sólo el build confirma los años. Revisa `Failed` y el informe JSON, no sólo el código
de salida del comando. Los chunks de cada resultado deben tener el año solicitado y la URL anual.

Reinicia la API después de indexar para que reconstruya su índice léxico en memoria. El selector
de año de la app sigue siendo manual: tener algún documento de 2026 no garantiza cobertura de
todas las preguntas de 2026. La calidad semántica de las respuestas requiere evaluación separada.

## Ampliar la cobertura

Para adquirir el catálogo de tarifas con límites explícitos:

```powershell
uv run taxguide crawl --source skatteetaten-rates-en `
  --year 2025 --year 2026 --max-pages 120 --max-depth 1

uv run taxguide corpus build `
  --url-prefix "/en/person/taxes/" --url-prefix "/en/rates/" `
  --language en --exclude-wizards --index
```

El catálogo se lee como JSON estático, sin ejecutar JavaScript. `max-pages` cuenta tanto páginas
base como variantes anuales; 120 no asegura descargar todo el catálogo. Los límites de robots,
rutas, tamaño y reintentos siguen activos. El catálogo puede contener impuestos fuera del ámbito
personal; para una colección curada, adquiere URLs concretas con el primer comando.
La página directorio puede fallar parsing por no contener texto de artículo; sus enlaces y las
tarifas descargadas se procesan independientemente. Los fallos no se ocultan.

Repetir el build sobre la misma colección omite embeddings de versiones completas que coinciden.
No borra documentos que hayan quedado fuera de la selección ni limpia artefactos anuales
previamente indexados sin verificación. Para sanear una colección anterior, construye una candidata
limpia con `--collection taxguide_annual_candidate_v1`, revisa sus fallos/cobertura y promoción
según [el ciclo del índice](index-lifecycle.md). No cambies de modelo de embeddings en una colección
existente. No hay fallback automático a otro año.

## Por qué parecía haber una pausa por documento

`corpus build` no tiene `sleep` entre documentos y no descarga páginas. El `request_delay: 0.75`
de `crawler` regula sólo descargas de la web; `--delay 0` lo desactiva, pero no acelera el build.
Mantén una cadencia razonable con el sitio oficial. Los timeouts son límites máximos de espera,
no pausas que se consuman siempre.

El script local `scripts/crawl_rates_v1.sh` también contiene una pausa de 0,5 s entre comandos
de descarga. No se ha modificado: esa pausa no forma parte de `corpus build`.

En este portátil Windows se midieron tres consultas `scroll` con el cliente real de Qdrant:

| Dirección | Tiempo por consulta |
| --- | --- |
| `localhost:6333` | 2,040–2,058 s |
| `127.0.0.1:6333` | 0,012–0,047 s |

Medición diagnóstica del 27-09-2026, no benchmark general ni aceleración prometida del pipeline.
El resultado es compatible con una espera de conexión/resolución IPv6 antes de llegar a IPv4.
`configs/base.yaml` usa ahora `127.0.0.1` para Qdrant y Ollama locales. Los endpoints remotos y
el LLM del sobremesa no cambian. Si usas overlays o variables de entorno, comprueba que no
reintroduzcan `localhost`. Las conexiones guardadas en `/settings` son sólo de la API, no del CLI;
actualízalas también si procede, conservando modelo y colección, y reinicia la API para YAML.

El informe separa `ingestion`, `chunking`, `index_lookup`, `embedding`, `index_upsert` e
`index_prune`. Si domina `embedding`, el coste es inferencia: bajar timeouts no lo acelera.
El tamaño de lote se controla con `corpus.embedding_batch_size` (32); no aumenta automáticamente
la velocidad en CPU ni agrupa varios documentos. Reducirlo ayuda si falta memoria.

## Verificación realizada

Se descargaron realmente la página general y sus versiones 2025/2026 de la deducción mínima,
en `data/annual-rates-verification/`, separado del corpus habitual. El build local produjo 15
chunks de 3 documentos, sin fallos: un documento por año más uno sin año. No se indexó esa
prueba en la colección activa ni se ejecutó generación LLM. Los tests deterministas cubren
selección anual, rechazo de años falsos, identidad separada y filtrado sin mezclar años.
