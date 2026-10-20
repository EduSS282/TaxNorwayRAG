# Despliegue de Fieldmind en GCP

Esta carpeta es autónoma: no necesita el código fuente ni compilar imágenes en la VM.
Usa el proyecto `eduardo-taxnorge`, la VM `taxnorge-vm` en `europe-north1-a`, imágenes Linux
`amd64`, Gemini `gemini-3.5-flash` en la ubicación **`eu`**, embeddings y reranking locales en CPU.
La región de la VM y la ubicación multirregional de Gemini son valores distintos.

## 1. Conectarse desde Windows

Instala [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk#windows).
Abre una nueva PowerShell y ejecuta:

```powershell
gcloud auth login eduardo.sanchezsarsa@gmail.com
gcloud compute ssh taxnorge-vm --project=eduardo-taxnorge --zone=europe-north1-a --tunnel-through-iap
```

El login del navegador es interactivo. La primera conexión puede crear una clave SSH y pedir
su confirmación. Usa la cuenta a la que Pierre ha concedido permisos; no crees claves de cuenta
de servicio ni ejecutes `gcloud auth application-default login` dentro de la VM.

## 2. Copiar el paquete

Desde la PowerShell de tu ordenador, en el directorio donde tengas `fieldmind-gcp.tar.gz`:

```powershell
gcloud compute scp .\fieldmind-gcp.tar.gz taxnorge-vm:~/fieldmind-gcp.tar.gz --project=eduardo-taxnorge --zone=europe-north1-a --tunnel-through-iap
```

Dentro de la sesión SSH, comprueba primero que `/data` está montado y que Docker usa ese disco:

```bash
findmnt /data
sudo docker info --format '{{.DockerRootDir}}'
df -h /data
```

El directorio de Docker debe ser `/data/docker`. Si el disco no está montado o el directorio
es otro, consulta a Pierre antes de descargar modelos. El paquete no cambia discos, IAM ni firewall.

Para una primera instalación:

```bash
sudo mkdir -p /data/taxnorge
sudo chown "$(id -u):$(id -g)" /data/taxnorge
tar -xzf ~/fieldmind-gcp.tar.gz -C /data/taxnorge
cd /data/taxnorge/fieldmind-gcp
umask 077
cp -n .env.example .env
nano .env
```

En `.env`, rellena `TAXGUIDE_ADMIN_TOKEN` con un token aleatorio de al menos 32 caracteres.
Puedes generarlo con `openssl rand -hex 32` en la VM y copiarlo al editor. Conserva el namespace
y la versión de imágenes que proporciona el paquete. No compartas ese token en logs o capturas.

Si ya existe una instalación, no extraigas otro paquete sobre una `.env` ni un `vertex.yaml`
personalizados sin revisarlos primero. La carpeta tiene su propio proyecto Compose
`taxnorge-fieldmind`; no adopta los volúmenes de la demo genérica.

## 3. Arrancar en la VM

Desde `/data/taxnorge/fieldmind-gcp`:

```bash
sudo docker compose config --quiet
sudo docker compose pull
sudo docker compose up -d --no-build
sudo docker compose ps -a
```

El frontend publica **`8080:3000`** en la interfaz de la VM, necesario para el túnel IAP directo.
Qdrant, Ollama, API y reranker no publican puertos en el host. Esta configuración presupone las
reglas de firewall de Pierre: VM sin IP pública y entrada al 8080 limitada a IAP. No añadas reglas
abiertas a Internet. IAP controla quién puede establecer el túnel; el token de operador protege
las acciones administrativas. Las consultas no tienen autenticación propia en la aplicación.

La primera ejecución descarga únicamente `qwen3-embedding:0.6b` en Ollama y los pesos del reranker
en su caché. **No descarga un LLM de generación.** `models-init` debe terminar con código cero;
el reranker puede tardar en descargar y cargar su modelo. La UI puede estar disponible antes.

```bash
sudo docker compose logs --tail=50 models-init reranker api
sudo docker compose stats --no-stream
df -h /data
```

Los volúmenes persisten bajo el data-root de Docker en `/data/docker`. Los logs de contenedor
tienen rotación. La configuración no modifica el Ops Agent; no presupone que este recoja todos
los logs de contenedor. Los 4 vCPU / 16 GB / 50 GB son el hardware facilitado, no un rendimiento
certificado: comienza con un corpus pequeño y prepara/indexa antes de hacer consultas concurrentes.

## 4. Abrir la interfaz desde tu ordenador

En **otra PowerShell local**, deja abierto este comando:

```powershell
gcloud compute start-iap-tunnel taxnorge-vm 8080 --local-host-port=localhost:8080 --zone=europe-north1-a --project=eduardo-taxnorge
```

Abre **http://localhost:8080**. Pierre y Marte usan el mismo comando con sus cuentas autorizadas.
No tienen que ejecutar el SSH ni conocer el token de operador para consultar la aplicación.
Cerrar la PowerShell del túnel interrumpe ese acceso local, sin detener los contenedores.

## 5. Preparar y comprobar la demo

1. En `/settings`, desbloquea con el token de `.env`. El estado inicial debe mostrar proveedor
   `vertex_ai`, modelo `gemini-3.5-flash`, proyecto `eduardo-taxnorge` y ubicación `eu`.
2. Comprueba conexiones. La prueba de Vertex obtiene ADC; no demuestra permisos de inferencia,
   cuota, disponibilidad del modelo ni calidad. No introduzcas credenciales GCP en el navegador.
3. En `/crawler`, descarga un corpus acotado y construye/indexa sus documentos.
4. Haz una pregunta sustentada por ese corpus y comprueba respuesta, citas y contexto. Esta es
   la primera comprobación real de generación y tiene el coste normal de una petición a Vertex.
5. Prueba reranking y mide sus tiempos. Detén la preparación antes de la sesión con los revisores.

La API usa ADC de `taxnorge-vm@eduardo-taxnorge.iam.gserviceaccount.com` a través del servicio de
metadatos. Su origen autorizado para generación es **`https://aiplatform.eu.rep.googleapis.com`**;
no se configura fallback a `global`. Las variables del SDK `google-genai` no son necesarias: el
proyecto usa su adaptador REST nativo. El presupuesto de thinking queda sin especificar para no
enviar un `thinkingBudget: 0` incompatible; el máximo de salida es 4096 tokens y debe ensayarse.

Las conexiones guardadas en el volumen tienen prioridad sobre el YAML tras una edición en la UI.
Si después cambias el YAML, revisa también `/settings`. Cambiar la ubicación de generación a otra
región/origen no autorizado se rechaza. Los permisos de IAM y las restricciones regionales siguen
siendo responsabilidad del proyecto GCP; el paquete no certifica por sí mismo residencia de datos.

## Actualizar, detener y resolver problemas

Si hay un `compose.override.yaml` con una imagen correctiva local de la API, ese archivo
tiene prioridad sobre la etiqueta de `.env`. Conserva el correctivo hasta que la versión
publicada incluya el cambio. Para volver a la imagen de `.env`, guarda el override con otro
nombre y recrea únicamente la API:

```bash
mv compose.override.yaml compose.override.yaml.disabled
sudo docker compose up -d --no-deps --wait api
```

Tras actualizar el chunking de rates, reutiliza las descargas y ejecuta la preparación con
prefijo `/en/rates/`, límite suficiente y escritura en la colección existente. Al terminar,
recrea la API si ya habías usado búsqueda híbrida: su índice BM25 se carga en memoria.
El reranker local usa CPU; un HTTP 503 también puede ser un timeout de ese servicio, antes
de llamar a Gemini. La presencia de datos indexados no garantiza que dense seleccione todos
los fragmentos relevantes ni que el reranker termine dentro del tiempo configurado.

Para actualizar imágenes, elige una versión publicada en `.env` y repite `pull` y
`up -d --no-build`. No necesitas compilar ni borrar los volúmenes. `sudo docker compose stop`
detiene la aplicación y conserva los datos; no detiene ni elimina la VM ni su disco. Coordina
con Pierre el apagado de recursos y las copias. No uses `down -v` para una actualización.

Si falla el SSH o el túnel, comparte con Pierre el mensaje de `gcloud`: puede requerir ajustar
OS Login/IAP. Si el túnel no alcanza el puerto, comprueba en la VM `curl -I http://localhost:8080`
y `sudo docker compose ps`. Si Vertex falla, revisa modelo, ubicación e identidad con Pierre;
no cambies a `global` para sortear una restricción. No compartas tokens ni cuerpos de peticiones.

Las pruebas automáticas usan dependencias controladas. Validan el endpoint, el empaquetado y las
fronteras de la aplicación, no el acceso real a esta VM, su IAM, los modelos ni la precisión fiscal.
Este paquete no se conecta ni despliega nada automáticamente.

Referencias: [endpoints de Vertex](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations),
[IAP TCP forwarding](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding).
