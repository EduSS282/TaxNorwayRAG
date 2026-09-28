# Crawler desde la aplicación

Abre **http://127.0.0.1:3000/crawler** o el enlace **Corpus / Crawler** de la página principal.
Permite elegir secciones, ver capturas existentes, descargar y cancelar. No necesita LLM,
embeddings, reranker ni Qdrant; sí acceso de la máquina de la API a Skatteetaten.

## Arranque

Desde la raíz del repositorio, en la terminal de la API:

```powershell
$crawlerSecret = Read-Host "Clave de administración (mínimo 32 caracteres)" -AsSecureString
$env:TAXGUIDE_ADMIN_TOKEN = [System.Net.NetworkCredential]::new("", $crawlerSecret).Password
uv run uvicorn taxguide.api.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Usa la misma clave de `/settings`, si ya la tienes configurada. No hace falta un perfil de
arranque de modelos. Ejecuta **un solo worker**. Si la API estaba arrancada antes de incorporar
esta funcionalidad, reiníciala; una API antigua devolverá 404 para `/v1/crawl`.

En otra terminal:

```powershell
cd frontend
npm ci
npm run dev
```

No ejecutes `npm ci` sobre un frontend activo en Windows: detén primero ese proceso para evitar
archivos nativos bloqueados. Para producción local: `npm run build` y después `npm start`, con
el servidor de desarrollo detenido. La clave se introduce en el panel; solo permanece en memoria
de esa página. No se guarda en cookies ni almacenamiento del navegador.

## Selección y descarga

El catálogo compartido con la CLI está en `configs/sources.yaml`. Incluye doce secciones inglesas:
tarifas/límites, declaración, tarjeta fiscal/anticipos, bancos/préstamos, vivienda/bienes y
donaciones/herencias, además de las seis siguientes:

| Sección | ID para `--source` |
| --- | --- |
| Ingresos, patrimonio y residencia en el extranjero | `skatteetaten-abroad-en` |
| Empleo, prestaciones y pensiones | `skatteetaten-employment-en` |
| Trabajadores extranjeros y PAYE | `skatteetaten-foreign-workers-en` |
| Acciones y valores | `skatteetaten-shares-en` |
| Familia y salud | `skatteetaten-family-en` |
| Liquidación, devoluciones y reclamaciones | `skatteetaten-assessment-en` |

Pulsa **Actualizar inventario** para cargar el catálogo actualizado; no necesitas reconstruir el
frontend. Si utilizas `TAXGUIDE_SOURCES_FILE`, actualiza ese catálogo personalizado también.
El límite sigue siendo **8 secciones por trabajo**, no 8 secciones en todo el catálogo.

Exit tax pertenece al ámbito de `skatteetaten-abroad-en`, no al de donaciones. Su enlace se puede
descubrir desde «Moving abroad» con profundidad 2, sujeto al límite de páginas. La fuente de
trabajadores extranjeros parte de la guía de trabajo, no de todo `/en/person/foreign/`; permite
explícitamente la rama fiscal PAYE enlazada fuera de esa guía. Los demás enlaces cruzados siguen
excluidos si no coinciden con los prefijos autorizados. Algunas capturas, como PAYE, pueden figurar
en dos secciones con ámbitos solapados; no sumes sus conteos como documentos únicos globales.

Ejemplo CLI, sin modificar las capturas por el mero hecho de añadir la fuente:

```powershell
uv run taxguide crawl --source skatteetaten-abroad-en --max-pages 50 --max-depth 2
uv run taxguide crawl --source skatteetaten-foreign-workers-en --max-pages 50 --max-depth 2
```

Los títulos del panel están en español; el contenido no se traduce.
El operador puede editar ese archivo o definir `TAXGUIDE_SOURCES_FILE` antes de iniciar la API.
El campo opcional `title` es la etiqueta visual; `id` mantiene la identidad estable.

1. Desbloquea el panel para consultar el inventario. Abrirlo no inicia descargas.
2. Marca secciones individualmente o pulsa **Seleccionar sin descargas**. Ninguna se omite
   automáticamente por tener capturas: puedes volver a descargar para actualizarla.
3. Ajusta páginas por sección (1–200, predeterminado 50) y profundidad (0–3, predeterminado 2).
   Se admiten hasta 8 secciones por trabajo, ejecutadas secuencialmente.
4. Opcionalmente indica hasta 5 años únicos, por ejemplo `2025, 2026`. Solo expande variantes
   anunciadas por el selector oficial de tarifas; no etiqueta guías generales con esos años.
   Las variantes y los intentos fallidos cuentan para el límite por sección.
5. Pulsa **Descargar**. Mientras el trabajo está activo, el panel consulta su estado cada
   2 segundos. Muestra descargas, fallos, omisiones y, al terminar cada sección, nuevas,
   modificadas y sin cambios. **Actualizar inventario** vuelve a comprobar los archivos.
6. **Cancelar descarga** conserva lo guardado. Puede esperar a la petición en curso; las pausas
   entre peticiones y reintentos son interrumpibles. Cerrar/bloquear la página no cancela el trabajo.

No se aceptan URLs, directorios, comandos ni retrasos arbitrarios desde el navegador. El catálogo
de la API solo admite dominios oficiales de Skatteetaten. Cada fuente limita sus rutas, idioma y
redirecciones; el crawler reutiliza `robots.txt`, límites de respuesta, timeouts y reintentos.
La pausa `crawler.request_delay` se configura en YAML (0,75 s en la base), no se elimina desde la UI.

## Qué significa «ya lo tengo»

El inventario usa los directorios **de la configuración YAML efectiva de la API**:

- `corpus.crawl_manifest_directory`: manifiestos, por defecto `data/manifests/crawl`.
- `corpus.raw_directory`: HTML, por defecto `data/raw/skatteetaten`.

Reconoce capturas antiguas de la CLI aunque no tengan `source_id`: comprueba la URL final contra
el ámbito de la sección. Cuenta identidades únicas con manifiesto válido, respuesta HTML correcta
y archivo cuyo SHA-256 coincide. Revalida el selector HTML para mostrar los años. Un archivo
ausente/dañado aparece como no disponible; un manifiesto ilegible se indica aparte. Durante una
escritura puede observarse temporalmente el par HTML/manifiesto a medio actualizar: refresca
tras finalizar. La última captura no garantiza que el contenido siga vigente hoy.

**Descargado no significa sección completa, año completamente cubierto, ni corpus indexado.**
«Finalizado» significa que terminó ese recorrido limitado; «con omisiones o errores» incluye
enlaces pendientes por límite, bloqueos robots/idioma y errores. Los límites de profundidad pueden
dejar páginas sin visitar aunque el trabajo figure finalizado. No se cuenta ni verifica Qdrant.

## Después: construir e indexar

Desde la raíz, con embeddings y Qdrant disponibles, por ejemplo para tarifas:

```powershell
uv run taxguide corpus build --url-prefix "/en/rates/" --language en --dry-run
uv run taxguide corpus build --url-prefix "/en/rates/" --language en --index
```

Elige los prefijos correspondientes a las secciones descargadas. Si la API usa un YAML/overlay
personalizado, pasa los mismos archivos mediante las opciones CLI `--config`/`--overlay` del
build. Las conexiones guardadas desde `/settings` **no se aplican al CLI**: alinea también sus
URLs, modelo y colección antes de indexar. Véanse [corpus](corpus.md) y [años](annual-corpus.md).

## Portátil, sobremesa y Oracle

La descarga ocurre donde corre **Python**, no donde abres el navegador ni donde corre Next.js.
Con API en el portátil y LLM en el sobremesa, las capturas se guardan en el portátil y no usan GPU.
Si Oracle hace el crawl por CLI, sincroniza HTML **y** manifiestos a los directorios de la API
antes de actualizar el inventario. No existe inventario distribuido, sincronización automática
ni control remoto de la CLI Oracle desde este panel.

## Contrato HTTP y límites operativos

`POST /v1/crawl` exige la misma clave y política de origen que `/v1/admin`; el navegador utiliza
el proxy `/api/crawl`. Respuestas sin caché:

| Acción | Campos | Respuesta |
| --- | --- | --- |
| `get` | `action` | `sections`, `invalid_manifests`, último `job` o null |
| `status` | `action` | `job`; `sections: null` evita releer HTML en cada sondeo |
| `start` | `sources`, opcionales `years`, `max_pages`, `max_depth` | Snapshot del trabajo aceptado; no espera su finalización |
| `cancel` | `job_id` | Snapshot con solicitud de cancelación; ID antiguo devuelve 409 |

Estados del trabajo: `running`, `cancelling`, `completed`, `partial`, `failed`, `cancelled`.
Solo un trabajo web puede estar activo; otro inicio devuelve 409. Entradas inválidas devuelven
422; clave incorrecta 401; origen de navegador directo 403; administración desactivada 503.
Un timeout del cliente no demuestra que el inicio fallase: consulta el inventario antes de repetir.
Un error de sondeo pausa la actualización automática hasta una actualización manual.

El trabajo vive en memoria: conserva capturas, pero no historial/progreso tras reiniciar la API,
ni reanudación automática. El apagado normal solicita cancelación y espera al trabajador antes
de soltar su bloqueo de escritura. El bloqueo `.crawler-manager.lock` del directorio de manifiestos
impide dos gestores web sobre el mismo corpus. **No coordina crawls CLI, sincronizaciones ni
builds externos**: no los ejecutes sobre esos directorios durante una descarga web.
No borra archivos ni implementa programación recurrente, colas distribuidas o cuentas por usuario.

La suite Python usa HTTP simulado y directorios temporales para verificar API → crawler →
capturas → inventario. Playwright comprueba selección, progreso, cancelación, errores, proxy y
vista móvil con un upstream de pruebas. No mide cobertura real de Skatteetaten ni calidad RAG.
