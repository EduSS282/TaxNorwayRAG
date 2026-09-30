# Interfaz local: abrir y usar TaxGuide Norway

La interfaz de los issues #73–#78 está en `frontend/`: Next.js App Router, React y TypeScript.
El backend fiscal sigue siendo Python. No hay datos simulados en la aplicación: las respuestas
vienen de la API configurada; las fixtures solo se usan en pruebas.

## Arranque local

Requisitos: Python 3.12+, uv, Node.js 20.9+ (CI usa Node 24), npm y los servicios de
[runtime local](local-runtime.md). Para una respuesta generada hacen falta corpus indexado,
embeddings, Qdrant y generador. El modo reranked y la comparación requieren además reranker.

1. Desde la raíz: `uv sync --locked`. Prepara los modelos y el corpus según el README; la UI no
   descarga pesos ni indexa documentos.
2. Terminal de API, desde la raíz:

   ```powershell
   uv run uvicorn taxguide.api.app:app --host 127.0.0.1 --port 8000 --no-access-log
   ```

   Si usas un overlay, define `$env:TAXGUIDE_OVERLAY = "configs/desktop.yaml"` antes del comando
   (ese nombre es ilustrativo, no un archivo incluido). Las rutas YAML siguen siendo relativas a
   la raíz. Los detalles están en [API](api.md).

3. Otra terminal:

   ```powershell
   cd frontend
   npm ci
   npm run dev
   ```

4. Abre **http://127.0.0.1:3000**. Detén cada proceso con Ctrl+C cuando termines.

Por defecto el proxy usa `http://127.0.0.1:8000`. Si necesitas cambiarlo, configura
`TAXGUIDE_API_URL` en el entorno de Node o en `frontend/.env.local`, siguiendo `.env.example`.
Es una variable de servidor: no uses `NEXT_PUBLIC_`. Reinicia Next.js al cambiarla. Se utiliza
el origen de la URL (sin prefijos de ruta); solo se admiten HTTP/HTTPS sin credenciales.

Para uso habitual, compila una vez y sirve sin recarga de desarrollo:

```console
cd frontend
npm ci
npm run build
npm start
```

No ejecutes `dev` y `build` simultáneamente sobre el mismo directorio `.next`. El frontend y la
API escuchan en loopback; las consultas siguen sin autenticación. Para sobremesa + portátil + Oracle consulta
[el despliegue de tres máquinas](three-machine-deployment.md#abrir-la-app-en-sobremesa-y-portátil).

## Flujo de uso

- Escribe una pregunta de hasta 4000 caracteres, sin nombres, números de identidad ni datos
  personales. Se envía a tus servicios configurados; «local» no convierte un endpoint remoto
  configurado por el operador en un endpoint privado.
- Selecciona un año entero entre 1900 y 2100 o déjalo vacío para la resolución/clarificación de
  la API. No es un catálogo de años indexados. Un año que contradiga la pregunta devuelve 422.
- Selecciona English, Norsk bokmål o Español. Cambia los textos de la interfaz y solicita ese
  idioma al generador. No traduce las fuentes ni filtra el corpus por idioma. Los mensajes
  deterministas de aclaración/abstención pueden seguir en inglés; no se verifica la traducción.
- Pulsa «Buscar respuesta». La interfaz diferencia respuesta, aclaración, abstención y error.
  Si `routing.classification.intent` es `uncertain`, pide aclarar el ámbito fiscal sin ejecutar
  retrieval ni generación; elegir un año no elimina esa ambigüedad. Es un nuevo valor del enum
  HTTP, no un nuevo estado visual. El inspector sigue siendo una búsqueda independiente.
  Las citas muestran ID, título, URL original y chunk; solo HTTP(S) se convierte en enlace.
  La confianza es del modelo, no una probabilidad calibrada de exactitud.
- Al editar pregunta, año, idioma o controles del inspector se borran resultados anteriores para
  no presentarlos como pertenecientes a una configuración nueva. No se conserva historial.

## Conexiones y servicios

El enlace «Conexiones y servicios» abre `/settings`. Sigue primero la
[preparación del administrador](runtime-management.md): clave en el backend, destinos permitidos
y perfiles locales de ejecutables/modelos. El panel se mantiene bloqueado hasta introducir la
clave; se guarda solo en memoria de esa página, no en almacenamiento del navegador.

Puedes editar y comprobar un borrador, guardar conexiones sin reiniciar la API, restaurar la
configuración anterior y consultar estados. Con perfiles válidos puedes iniciar/parar servicios
locales o pulsar «Preparar servicios» para el modo elegido. Una parada requiere confirmación.
Si una dependencia está arrancando, espera y pulsa «Comprobar servicios»; vuelve a preparar cuando
esté lista. No hay arranque automático al abrir el panel ni descarga de modelos.

«Local» es la máquina de Python, aunque abras la app desde el portátil. Los destinos remotos se
pueden configurar y comprobar, pero su arranque sigue siendo manual. Los cambios del panel afectan
solo a la API, no al YAML del CLI. El panel de administración está en español.

## Crawler y corpus

El enlace **Corpus / Crawler** abre `/crawler`. Usa la misma clave de administración para ver
capturas existentes y seleccionar fuentes del catálogo. Permite descargar varias secciones,
seleccionar años de tarifas, limitar páginas/profundidad, consultar progreso y cancelar conservando
archivos. No requiere modelos ni Qdrant. Las capturas se guardan donde corre Python.
El panel distingue descarga de indexación: **no asegura cobertura completa ni consulta Qdrant**.
El build/index sigue por CLI. Consulta [el manual del crawler web](crawler-ui.md) para arrancarlo,
entender los conteos y alinear directorios/conexiones. Reinicia una API antigua para habilitar la ruta.

## Inspector (#78)

Abre «Inspector de retrieval para desarrolladores». Puedes cambiar dense / hybrid / hybrid +
rerank para la respuesta. Activa «Incluir contexto final en la respuesta» antes de preguntar:
el panel mostrará los chunks realmente seleccionados por `ContextBuilder`, sus IDs S1…, puntuación,
texto, año, idioma y procedencia. Si el servicio terminó antes de construir contexto no hay panel;
si construyó uno vacío, se muestra vacío. Las fuentes citadas son un subconjunto distinto del
contexto disponible, no todos los resultados recuperados.

«Comparar retrieval» llama a `/v1/retrieve` con `mode: all` y muestra dense, sparse, fused y
reranked, cinco resultados por etapa y el límite de candidatos configurado en la API (diez en
`configs/base.yaml`). La respuesta también respeta ese límite. Requiere todos los servicios y puede
ser costoso. Las cuatro búsquedas se ejecutan de manera independiente; no representan los pasos
capturados de la misma respuesta. Las escalas de puntuación no son comparables entre etapas.
Puedes tener respuesta/contexto y comparación visibles para la misma pregunta; sus trace IDs
se muestran por separado. No hay persistencia de trazas ni evaluación automática de calidad.

## Diagnóstico

| Síntoma | Comprobación |
| --- | --- |
| No abre 3000 | Proceso Node y puerto; usa la dirección loopback de la máquina o el túnel |
| HTTP 502 | API no accesible desde Node, URL incorrecta, respuesta no JSON o timeout del proxy |
| HTTP 503 | API activa pero Qdrant/modelo/configuración no disponibles; revisa logs con trace ID |
| HTTP 422 | Año contradictorio, límites o entrada rechazados por la API |
| Abstención | No se alcanzó evidencia válida suficiente; no es necesariamente un fallo de red |
| Funciona dense pero no comparar | Verifica BM25/corpus y reranker, además de embeddings/Qdrant |

El proxy espera hasta 180 segundos y el navegador 190; un timeout no garantiza que se cancele
el cómputo Python ya iniciado. Las solicitudes son sin caché, sin reintentos automáticos y no
reenvían cookies ni cabeceras del navegador a la API, excepto `Authorization` exclusivamente para
`/api/admin` y `/api/crawl`. Solo están permitidas query, retrieve, admin y crawl en el backend fijo. Se
rechazan peticiones con origen explícito distinto; esto no sustituye autenticación o protección
de un despliegue público. No expongas estos servicios sin una pasarela autenticada.

El cliente del crawler espera 30 segundos por operación de control; la descarga corre en segundo
plano sin mantener esa petición abierta. Sondea cada 2 segundos solo mientras haya un trabajo
activo y el panel permanezca desbloqueado. Un error pausa el sondeo hasta actualizar manualmente.

## Verificación y límites

Desde `frontend/`:

```console
npm ci
npm run typecheck
npm run build
npx playwright install chromium
npm test
```

En Windows PowerShell, si la política bloquea `npm.ps1` o `npx.ps1`, usa `npm.cmd` y `npx.cmd`
para los mismos comandos. Ejecuta una sola suite Playwright a la vez: los puertos de prueba
13000 y 18001 deben estar libres; no reutilices una instancia de la aplicación real.

Playwright usa los puertos loopback 13000 y 18001 y comprueba la UI compilada contra un upstream
de pruebas: formulario, idioma/año, citas, contexto, comparación, estados vacíos/de error,
loading, vista móvil y controles del proxy. No se conecta a los modelos reales. Los tests Python
comprueban por separado API → servicio → prompt/contexto con dependencias inyectadas. CI ejecuta
ambos grupos. La revisión visual y estos tests no reemplazan el benchmark de corpus/modelos reales,
que sigue pendiente. También se prueban desbloqueo, borradores, guardado/restauración, controles de
servicios y aislamiento de la clave en el proxy. No hay chat persistente, cuentas, despliegue
público, descargas de modelos ni control de procesos remotos.
Los tests del crawler cubren inventario, selección, años, progreso/cancelación, reconexión a trabajo
activo, errores y vista móvil; usan fixtures, no descargan el sitio oficial ni evalúan respuestas RAG.
El [despliegue Docker privado](production-readiness.md) compila la misma interfaz y apunta el
proxy a la API por la red interna de Compose. No inicia modelos ni sustituye los benchmarks
reales; los tests Playwright siguen usando un upstream determinista. La prueba de despliegue en
CI verifica el proxy y una aclaración determinista, no inferencia con modelos.
