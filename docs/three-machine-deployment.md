# Ejecución distribuida en sobremesa, portátil y Oracle Free Tier

Esta guía convierte la arquitectura actual de TaxGuide Norway en un despliegue operativo para el
hardware disponible:

- sobremesa: GTX 1060 con 6 GB de VRAM y 32 GB de RAM DDR4;
- portátil: Intel i7-13700H y 16 GB de RAM DDR5;
- Oracle Free Tier: 2 OCPU y 12 GB de RAM.

La recomendación no presupone una API web todavía. El punto de entrada implementado es la CLI
`taxguide`; Qdrant, Ollama y llama.cpp son procesos externos que TaxGuide consume por HTTP.

## Decisión recomendada

Empieza con el camino interactivo completo en el sobremesa y usa las otras máquinas para descargar
trabajo auxiliar. Esta distribución minimiza la latencia y evita que una caída de Internet impida
responder preguntas locales.

| Máquina | Responsabilidad recomendada | Procesos |
| --- | --- | --- |
| Sobremesa | Orquestación y respuesta interactiva | TaxGuide CLI, Qdrant, embeddings y generador |
| Portátil | Desarrollo, pruebas y reranking opcional | repositorio, pytest/Ruff/mypy, llama.cpp reranker en CPU |
| Oracle VM | Trabajo persistente no interactivo | crawling programado, informes, sincronización y copias |

```text
                    trabajo offline
Oracle VM ──crawl/manifests──► sobremesa ──embed/index──► Qdrant
                                  │                         │
                                  │ consulta                │ evidencia
                                  ▼                         │
                       TaxGuide CLI ◄───────────────────────┘
                          │       │
                          │       └──► llama.cpp 4B, GTX 1060 ──► respuesta estructurada
                          │
                          └──► portátil, reranker 0.6B CPU (opcional)
```

No pongas la VM en el camino crítico de una consulta. Dos OCPU son adecuados para crawling lento,
automatización y coordinación, pero no para servir de forma interactiva embeddings, reranking o un
LLM de 4B.

## Etapa 1: validar todo en el sobremesa

Esta es la primera configuración que debe funcionar de extremo a extremo. No distribuyas procesos
hasta obtener respuestas correctas y repetibles de esta etapa.

### 1. Preparar el repositorio

En PowerShell, desde la raíz del repositorio:

```powershell
uv sync --locked
uv run taxguide --help
nvidia-smi
ollama --version
```

TaxGuide requiere Python 3.12 o posterior. Los pesos de los modelos y los binarios de Ollama y
llama.cpp se gestionan fuera del proyecto.

### 2. Iniciar Qdrant

```powershell
docker compose up -d qdrant
Invoke-RestMethod -Uri "http://127.0.0.1:6333/healthz"
```

El volumen persistente queda en `data/qdrant`. El `compose.yaml` del repositorio es únicamente para
desarrollo local: publica Qdrant en el host y no debe copiarse sin cambios a una máquina expuesta a
Internet.

### 3. Iniciar embeddings

```powershell
ollama pull qwen3-embedding:0.6b

$embedBody = '{"model":"qwen3-embedding:0.6b","input":["dimension probe"]}'
$embedResponse = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:11434/api/embed" `
  -ContentType "application/json" `
  -Body $embedBody
$embedResponse.embeddings[0].Count
```

El primer `corpus build --index` crea la colección Qdrant con esa dimensión. Si cambias el modelo o
su dimensión, utiliza un nombre de colección nuevo; TaxGuide rechazará una colección incompatible.

### 4. Iniciar el generador en la GTX 1060

Usa una conversión GGUF fijada de `Qwen/Qwen3-4B-Instruct-2507`, inicialmente en Q4_K_M y con
contexto 4096:

```powershell
llama-server `
  -m C:\models\qwen3-4b-instruct-2507-q4_k_m.gguf `
  --alias Qwen/Qwen3-4B-Instruct-2507 `
  --host 127.0.0.1 --port 8080 `
  -c 4096 -ngl 99 --jinja
```

No aumentes el contexto ni atiendas varias generaciones simultáneas al principio. La GTX 1060 de
6 GB debe compartir memoria con el modelo de embeddings y el contexto del generador. Si aparece un
error de memoria:

1. mantén el generador Q4_K_M y contexto 4096;
2. ejecuta el reranker exclusivamente en el portátil;
3. reduce `corpus.embedding_batch_size` de 32 a 8 durante la indexación;
4. si aún hay contención, mueve los embeddings a CPU o evita indexar mientras generas respuestas.

No cambies a un modelo generativo mayor hasta medir latencia, RAM y VRAM con el corpus real.

### 5. Construir el corpus y responder

```powershell
uv run taxguide crawl `
  "https://www.skatteetaten.no/en/person/taxes/tax-return/" `
  --max-pages 25 --max-depth 2

uv run taxguide corpus build `
  --url-prefix "/en/person/taxes/" `
  --language en --dry-run

uv run taxguide corpus build `
  --url-prefix "/en/person/taxes/" `
  --language en --index

uv run taxguide retrieve `
  "What is the minimum standard deduction for 2025?" `
  --mode hybrid --limit 5

uv run taxguide answer `
  "What is the minimum standard deduction for 2025?" `
  --mode hybrid --json
```

Empieza con `hybrid`: no requiere reranker. Una ejecución correcta de `answer` devuelve
`answered`, `clarification_required` o `abstained`; `failed` indica un problema operativo. TaxGuide
nunca publica directamente el texto sin validar del modelo.

## Etapa 2: mover el reranker al portátil

El reranker es el proceso más razonable para separar. El modelo de 0.6B cabe en la RAM del portátil,
el i7-13700H puede ejecutarlo en CPU y la GTX del sobremesa queda reservada para generación.

### Opción recomendada: llama.cpp y túnel SSH

En el portátil, inicia el servicio ligado únicamente a loopback:

```powershell
llama-server `
  -hf ggml-org/Qwen3-reranker-0.6B-Q8_0-GGUF:Q8_0 `
  --embedding --rerank --pooling rank `
  --host 127.0.0.1 --port 8001 -ngl 0
```

Con un servidor SSH habilitado en el portátil, crea el túnel desde el sobremesa:

```powershell
ssh -N -L 8001:127.0.0.1:8001 usuario@IP_PRIVADA_PORTATIL
```

Mientras el túnel esté abierto, el sobremesa puede conservar `http://localhost:8001`. Crea, por
ejemplo, `configs/three-machines.yaml` como overlay local no secreto:

```yaml
project:
  environment: three-machines
corpus:
  embedding_batch_size: 8
retrieval:
  default_mode: reranked
  reranker_provider: llamacpp
  reranker_base_url: http://127.0.0.1:8001
  reranker_timeout: 120.0
  candidate_limit: 10
generation:
  base_url: http://127.0.0.1:8080
  evidence_max_tokens: 2400
  max_tokens: 1000
```

Pruébalo desde el sobremesa:

```powershell
uv run taxguide retrieve `
  "What is the minimum standard deduction for 2025?" `
  --mode reranked --candidate-limit 10 --limit 5 `
  --overlay configs/three-machines.yaml

uv run taxguide answer `
  "What is the minimum standard deduction for 2025?" `
  --mode reranked --candidate-limit 10 --limit 5 `
  --overlay configs/three-machines.yaml --json
```

El túnel evita abrir el puerto 8001 a toda la red. Si prefieres conexión LAN directa, enlaza el
reranker a la IP privada del portátil, permite el puerto solo desde la IP del sobremesa en el
firewall y cambia `reranker_base_url` a esa IP. No lo publiques mediante port forwarding del router.

### Alternativa Python

El repositorio también incluye un servicio FastAPI basado en `sentence-transformers`:

```powershell
uv sync --locked
uv run uvicorn taxguide.reranking.service:app --host 127.0.0.1 --port 8001
```

En ese caso configura `reranker_provider: http`. Esta opción es cómoda para desarrollo, pero
normalmente consume más RAM que el GGUF con llama.cpp. No ejecutes ambos rerankers a la vez.

## Etapa 3: usar Oracle para crawling programado

La VM debe contener únicamente documentación pública y artefactos operativos. No subas consultas
de usuarios, respuestas ni datos fiscales personales.

### Preparación en la VM

Ejemplo para una VM Linux con el repositorio en `/opt/taxguide`:

```bash
cd /opt/taxguide
uv sync --locked
uv run taxguide crawl --help
mkdir -p logs
```

El proyecto instala actualmente las dependencias en un único entorno, incluidas algunas de ML. En
una VM ARM puede ser necesario comprobar que existen wheels compatibles. Si la instalación completa
no cabe o no está soportada, mantén el crawling en el sobremesa hasta separar dependencias por rol;
no sustituyas paquetes fijados de forma silenciosa.

Una entrada de `crontab -e` para un crawl semanal limitado podría ser:

```cron
15 3 * * 1 cd /opt/taxguide && /usr/local/bin/uv run taxguide crawl "https://www.skatteetaten.no/en/person/taxes/tax-return/" --max-pages 50 --max-depth 2 >> /opt/taxguide/logs/crawl.log 2>&1
```

Antes de automatizar, ejecuta exactamente el mismo comando manualmente y revisa el manifiesto, los
códigos HTTP y el límite de páginas. No incrementes la frecuencia ni elimines el retardo configurado
sin revisar la política del sitio.

### Sincronizar el crawl con el sobremesa

Detén cualquier construcción de corpus concurrente y copia los artefactos producidos por el crawl:

```powershell
scp -r ubuntu@IP_ORACLE:/opt/taxguide/data/raw/skatteetaten data/raw/
scp -r ubuntu@IP_ORACLE:/opt/taxguide/data/manifests/crawl data/manifests/
```

Después, en el sobremesa, ejecuta primero `--dry-run`, revisa el informe y solo entonces indexa:

```powershell
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --language en --dry-run
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --language en --index
```

Qdrant permanece como fuente de verdad en el sobremesa. Los ficheros de Qdrant no deben copiarse
mientras la base de datos está escribiendo; para copias, detén Qdrant o usa un mecanismo de snapshot
compatible con la versión instalada.

## Uso opcional de Qdrant en Oracle

No es la configuración inicial recomendada. Solo tiene sentido si necesitas que varios clientes
accedan a un índice siempre encendido y ya has medido almacenamiento, memoria, latencia y copias.

La configuración actual de TaxGuide no contiene un campo para la API key de Qdrant. Hasta añadir
configuración autenticada, liga Qdrant a loopback en Oracle y accede mediante túnel SSH:

```powershell
ssh -N -L 6333:127.0.0.1:6333 ubuntu@IP_ORACLE
```

El cliente puede seguir usando `corpus.qdrant_url: http://127.0.0.1:6333`. No expongas los puertos
6333 o 6334 mediante las reglas públicas de Oracle Cloud.

## Orden de arranque diario

1. En el sobremesa, inicia Qdrant y comprueba `/healthz`.
2. Comprueba Ollama con la petición de embedding.
3. Inicia el generador y comprueba que escucha en el puerto 8080.
4. Solo para `reranked`, inicia el reranker en el portátil y abre el túnel.
5. Ejecuta una recuperación conocida antes de probar generación.
6. Ejecuta `taxguide answer` y conserva el JSON si estás midiendo resultados.

Para aislar fallos, comprueba en este orden:

```text
Qdrant → embedding de consulta → dense/hybrid retrieval → reranker → generator → answer
```

Si `hybrid` funciona y `reranked` no, el problema está en el portátil, el túnel o el adaptador del
reranker. Si `retrieve` funciona y `answer` no, revisa el generador, su nombre de modelo, el contexto
y la validez del JSON devuelto.

## Perfil inicial de operación

Mantén estos límites hasta tener benchmarks propios:

| Parámetro | Valor inicial |
| --- | --- |
| Generador | Qwen3-4B-Instruct-2507 GGUF Q4_K_M |
| Contexto de llama.cpp | 4096 tokens |
| Concurrencia generativa | 1 |
| Evidencia | 2400 tokens |
| Salida máxima | 1000 tokens |
| Candidatos para reranking | 10 |
| Resultado final | 5 chunks |
| Batch de embeddings en GTX 1060 | 8 inicialmente; aumentar después de medir |

Registra para cada prueba el commit Git, overlay, hash del GGUF, versión de llama.cpp/Ollama,
driver NVIDIA, colección Qdrant, corpus, latencia fría/caliente y picos de RAM/VRAM. Sin esos datos
no es posible comparar de forma fiable un cambio de modelo o de máquina.

## Qué no está automatizado todavía

- TaxGuide no inicia ni supervisa Qdrant, Ollama, llama.cpp o los túneles SSH.
- No existe failover automático entre sobremesa, portátil y Oracle.
- No existe todavía una API HTTP de consulta ni una interfaz web implementada.
- El cache de embeddings es local al proceso, no persistente y no está compuesto por la factory.
- No hay un benchmark real de corpus/generación con umbrales de release comprometido al repositorio.
- El servicio remoto de reranking no tiene autenticación propia.
- El despliegue distribuido depende de direcciones estáticas o túneles administrados por el operador.

Por estas limitaciones, la arquitectura de tres máquinas debe tratarse como entorno de desarrollo y
evaluación. El siguiente paso operativo razonable es estabilizar la etapa 1, medirla y mover solo el
reranker al portátil; Oracle se incorpora después para crawling y copias, no para inferencia.
