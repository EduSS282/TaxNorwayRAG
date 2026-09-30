# Conexiones y servicios desde la app

En la app, abre **Conexiones y servicios** (`/settings`). El panel permite probar, guardar y
restaurar conexiones, comprobar servicios y arrancar/detener procesos locales predefinidos.
«Local» significa **la máquina de la API Python**, no la máquina del navegador ni necesariamente
la del servidor Next.js. El control de otras máquinas por SSH/agentes no está implementado.

## 1. Habilitar la administración

Por defecto está desactivada. Crea una clave aleatoria de al menos 32 caracteres con tu gestor
de contraseñas. En la terminal PowerShell de la API, introduce esa clave sin mostrarla:

```powershell
$runtimeSecret = Read-Host "Clave de administración" -AsSecureString
$env:TAXGUIDE_ADMIN_TOKEN = [System.Net.NetworkCredential]::new("", $runtimeSecret).Password
```

No escribas la clave en un YAML, URL, archivo versionado o variable `NEXT_PUBLIC_`. Se usa una
clave compartida de operador, no un sistema multiusuario. La web la conserva solo en memoria
hasta bloquear el panel, navegar o recargar. No la guarda en cookies, localStorage ni sessionStorage.
La API no la reenvía a los procesos que arranca.

Los destinos del YAML base/overlay quedan autorizados inicialmente. Para poder seleccionar otros
servidores desde la web, autoriza previamente sus orígenes exactos, separados por comas:

```powershell
$env:TAXGUIDE_SERVICE_ORIGINS = "http://generator.example.invalid:8080,http://reranker.example.invalid:8001"
```

Los nombres `.invalid` son marcadores; sustitúyelos por tus destinos privados reales.
`localhost` y `127.0.0.1` son entradas distintas. Solo se admiten URLs
HTTP(S) sin credenciales, rutas (tampoco `/v1`), query o fragmento. La allowlist es intencional:
el panel no puede convertir el backend en un cliente HTTP hacia cualquier destino. Debe contener
servicios de confianza; los nombres DNS y su resolución también son responsabilidad del operador.
Los modelos externos que requieren API keys siguen necesitando un adaptador/pasarela apropiado;
la clave del panel no es una credencial para proveedores LLM.

## 2. Preparar perfiles locales una sola vez

Para editar conexiones no necesitas perfiles. Para habilitar **Iniciar**, copia
`configs/local-services.example.yaml` a `configs/local-services.yaml` y edítalo en el host de la API:

- `executable`: ruta absoluta de un binario nativo ya instalado (Ollama, llama-server o Docker).
- `model_path`: ruta absoluta de un GGUF existente para generador/reranker.
- `model_id`: alias correspondiente a ese GGUF; debe coincidir con el modelo guardado en la app.
  Cambiar el alias en la web no cambia los pesos del perfil ni puede disfrazar otro GGUF.
- `gpu_layers`: cero por defecto (CPU). Para tu GTX 1060, ajusta solo el generador después de
  medir memoria; deja reranker y embeddings gestionados en CPU. No se detecta VRAM automáticamente.
- `context_size`: contexto del proceso llama.cpp, distinto del presupuesto de evidencia de TaxGuide.
- `container`: nombre de un contenedor Qdrant **ya creado**, no una imagen que descargar.

Elimina del archivo los servicios que no quieras controlar. Los perfiles no son editables desde
la web: no se admiten comandos libres, argumentos arbitrarios ni rutas de ejecutables del navegador.
En Linux usa rutas como `/usr/local/bin/llama-server` y `/srv/models/model.gguf`, no las del ejemplo
Windows. Se usa el daemon Docker local estándar: named pipe de Docker Desktop en Windows o
`/var/run/docker.sock` en Linux; contextos Docker remotos y sockets rootless personalizados no se gestionan.

Para preparar Qdrant por primera vez, con Docker activo, desde la raíz:

```powershell
docker compose pull qdrant
docker compose create qdrant
docker compose ps -a
```

El primer comando descarga una imagen: ejecútalo conscientemente fuera de la app. Usa en el perfil
el nombre real del contenedor mostrado por `ps`. El Compose publica ahora los puertos solo en
`127.0.0.1`; un contenedor antiguo con puertos públicos se rechaza. Recrearlo para aplicar nuevos
bindings es una tarea manual con posible interrupción: conserva el volumen y comprueba tus copias.
El panel solo hace `start`/`stop` del contenedor configurado; no crea, descarga ni borra contenedores
o volúmenes. El puerto REST 6333 del contenedor debe apuntar al host/puerto configurado en la app.

Ollama debe tener el modelo instalado previamente. La app no ejecuta `ollama pull`; si falta un
modelo lo indica. Arrancar Ollama inicia su servidor, **no precarga** pesos. Un Ollama ya arrancado
por la aplicación de escritorio o el sistema se considera externo y nunca se detiene desde TaxGuide.

Activa los perfiles y arranca **un único worker**, sin `--reload` para operación habitual:

```powershell
$env:TAXGUIDE_LOCAL_SERVICES = "configs/local-services.yaml"
uv run uvicorn taxguide.api.app:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Abre el frontend normalmente y desbloquea `/settings` con tu clave. El frontend/API sigue usando
`TAXGUIDE_API_URL`, que no se modifica desde esta pantalla. Para acceso desde el portátil utiliza
el túnel de la [guía de tres máquinas](three-machine-deployment.md).

## 3. Guardar, probar y restaurar conexiones

El panel permite modificar las URLs, modelos, proveedor de embeddings/reranking, colección Qdrant
y timeout del generador (hasta 180 segundos, coherente con el proxy). **Probar conexiones** comprueba
el borrador sin guardarlo, sin inferencia y sin descargar pesos. **Guardar y aplicar** persiste y
reemplaza los adaptadores para nuevas consultas, sin reiniciar la API. Las consultas en curso
mantienen su snapshot anterior; no tienen failover automático.

El estado y una versión anterior se guardan juntos mediante reemplazo atómico en
`data/runtime/connections.json`. `TAXGUIDE_CONNECTIONS_FILE` permite elegir otra ruta al arrancar.
Protege este directorio y los perfiles con permisos del usuario de la API. La clave no se guarda
en ese archivo. Un bloqueo de archivo excluye otros workers usando el mismo estado; no ejecutes
varios gestores para el mismo equipo utilizando distintas rutas para eludir ese bloqueo.

**Restaurar configuración anterior** intercambia la configuración actual con la anterior. Las
revisiones impiden sobrescribir cambios realizados por otra pestaña; recarga ante un conflicto.
Antes de guardar/restaurar, detén los servicios que TaxGuide posea, para no dejar un proceso
gestionado apuntando a una configuración distinta.

Cambiar el modelo o proveedor de embeddings exige **otro nombre de colección** y marcar la
confirmación de reindexación. No se borra ni reindexa nada desde la app. Prepara la nueva colección
con el modelo correcto antes de consultar; para volver a la anterior se pide la misma confirmación.
Cambiar solo una URL no prueba que el modelo remoto sea idéntico. Si cambian los pesos/revisión
servidos tras una URL o alias, debes tratarlo como cambio de modelo y crear un índice compatible.

Estas preferencias afectan a la **API**, no a la CLI. Para construir/reindexar con `taxguide corpus`
prepara también un overlay YAML equivalente y usa `--overlay`; la CLI no lee automáticamente el
JSON de conexiones. Si desactivas administración, la API vuelve al YAML base/overlay y no carga
ese JSON. Al reactivarla vuelve a cargar el estado guardado; si contiene un destino retirado de la
allowlist, el arranque falla en lugar de contactar silenciosamente con él.

## 4. Preparar e iniciar servicios

**Preparar servicios para consultar** trabaja secuencialmente según el modo elegido:

| Modo | Dependencias |
| --- | --- |
| Dense / hybrid | Qdrant → embeddings → generador |
| Reranked | Qdrant → embeddings → reranker → generador |
| Sparse | Qdrant → generador |

Se detiene ante una dependencia no preparada. Si un proceso está arrancando, espera y pulsa
**Comprobar servicios**; después vuelve a preparar. No hay polling, reintentos ni arranque automático
al abrir la página. Elige también el modo correspondiente al volver al formulario de preguntas.
Si Qdrant está vacío o falta la colección, indexa primero; no se interpreta un puerto abierto como
evidencia de que el sistema puede contestar.

| Estado | Significado |
| --- | --- |
| `available` | Pasó la comprobación limitada descrita debajo |
| `starting` | Proceso propio vivo, pero todavía no pasa la comprobación; puede requerir corregir modelo/corpus |
| `external` | Puerto ocupado por un servicio no iniciado por TaxGuide; su disponibilidad se informa por separado |
| `in_process` | Adaptador Python local; no tiene botón de proceso externo ni se valida cargando pesos |
| `unavailable` / `error` | Endpoint/recurso ausente, perfil incorrecto o fallo de operación |
| `stopped` | El gestor detuvo el proceso que poseía |

Las comprobaciones leen: `/v1/models` y alias del generador; `/api/tags` y modelo instalado para
Ollama; `/health` para reranker; colección Qdrant verde y con puntos. No prueban inferencia,
dimensiones de embeddings, fidelidad fiscal ni compatibilidad completa del reranker.

Solo pueden arrancarse URLs HTTP de loopback (`127.0.0.1`, `localhost`, `::1`). Direcciones remotas
se prueban/usan, pero sus procesos deben arrancarse allí manualmente. Los proveedores Python
`local` siguen cargándose de manera perezosa dentro de la API y no se gestionan como procesos.
En esos adaptadores existentes, sentence-transformers puede descargar pesos ausentes al realizar
la primera consulta; prepara su caché y modo offline antes de utilizarlos si necesitas operación
sin red. Los botones de administración no provocan esa carga ni descarga.

El gestor bloquea dos perfiles llama.cpp propios con `gpu_layers > 0` simultáneos; Ollama gestionado
se configura en CPU y con un solo modelo cargado/una solicitud paralela. No es una reserva global
de RAM/VRAM: no controla aplicaciones externas ni evita por sí solo agotar memoria.

**Detener** exige confirmación y solo actúa sobre el handle del proceso hijo o la instancia exacta
del contenedor iniciada por este gestor. No adopta PIDs por puerto. Reiniciar un contenedor desde
otra herramienta revoca su propiedad. Si el daemon no responde se conserva el handle y se muestra
error, sin permitir un nuevo arranque a ciegas. Un cierre normal de la API detiene sus servicios;
tras un cierre forzado pueden quedar procesos externos que deberás revisar manualmente. Nunca se
readoptan automáticamente después de un reinicio de TaxGuide.

Los eventos recientes guardan únicamente acciones/errores del gestor y códigos de salida, en memoria.
No se captura la salida bruta de modelos para evitar exponer prompts o secretos. Para diagnosticar
un fallo nativo detallado, ejecuta manualmente el servicio en una terminal fuera del gestor.

## Seguridad y verificación

La clave solo protege `/v1/admin`; los endpoints de consulta existentes siguen sin autenticación.
Mantén ambos servidores en loopback o tras túnel/gateway privado con TLS donde corresponda. El
proxy verifica origen y solo reenvía `Authorization` hacia administración; la API rechaza llamadas
de navegador directas con `Origin`. No hay cuentas, auditoría persistente, rate limiting ni control
remoto de hosts. La cuenta del backend debe tener permisos mínimos para ejecutar sus perfiles.

Las pruebas Python inyectan procesos/HTTP simulados y cubren propiedad, bloqueo GPU, autenticación,
persistencia, rollback, allowlist, readiness y renovación de backend. Playwright cubre el panel y
el proxy con dobles de prueba. Ninguna prueba automática arranca tus modelos, descarga pesos o
modifica tus contenedores reales. Hace falta validar perfiles/rutas/recursos en tu hardware.

Referencias de los runtimes externos: [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
y [Ollama GPU](https://docs.ollama.com/gpu). Fija versiones compatibles con tus modelos antes de medir.
