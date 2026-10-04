<p align="right"><a href="PRIVACY.en.md">🇺🇸 English</a></p>

# Política de privacidad

Última actualización: 5 de octubre de 2026.

Comic Identify es una aplicación de escritorio de uso personal. No tiene servidor ni cuenta propios, y su
autor no recibe ningún dato de quien la usa.

## Qué datos trata

- **Tu colección de cómics:** las rutas de las carpetas que eliges, los nombres de los archivos, las portadas
  (para calcular su huella visual y leer el código de barras) y los metadatos `ComicInfo.xml` que la aplicación
  escribe en tus archivos.
- **Tus ajustes:** carpetas, patrón de nombres, comando del asistente de IA, carpeta de las copias de seguridad
  y, si la pones, tu clave de la API de ComicVine.
- **Registros de deshacer** de renombrados, metadatos y transferencias a GCstar.

## Dónde se guardan

Todo queda en tu equipo, en los directorios XDG de usuario:

- `~/.config/comic-identify/config.json`: ajustes y clave de ComicVine (en claro, protegido por permisos 600).
- `~/.local/share/comic-identify/`: índices locales (colección, Grand Comics Database, Universo Marvel y
  Tebeosfera), registros de deshacer y logotipos propios.
- `~/.cache/comic-identify/`: logotipos e iconos descargados, caché del panel web y carpeta de trabajo del asistente.
- Las copias de seguridad, en la carpeta que tú eliges.

## Con quién se comparte

Con nadie por parte de la aplicación. No incluye analítica, telemetría ni publicidad. La red solo se usa
cuando tú lo pides, y las peticiones salen de tu equipo hacia:

- **Grand Comics Database** (comics.org), **Universo Marvel**, **Tebeosfera** y **ComicVine**, para buscar y
  descargar fichas. A ComicVine se le envía tu clave de API y el texto de la búsqueda. A los demás, la consulta
  o la dirección de la ficha.
- Las webs de búsqueda y de compra que abres desde la aplicación, en el panel web integrado o en tu navegador.
  Esas webs tienen sus propias políticas; la aplicación bloquea en el panel la medición y la publicidad de
  Tebeosfera, y no guarda cookies en disco salvo la de acceso de comics.org, solo en memoria.
- **El asistente de IA es opcional y usa tu propia sesión.** Si lo activas, la aplicación ejecuta el comando
  que tú configuras (por defecto, `claude`) con un mensaje y la ruta de la portada. Lo que ese programa envíe
  a su servicio se rige por su propia política, no por esta.

Las portadas de tus archivos no se envían a ningún servidor de la aplicación, que no existe.

## Cómo borrar tus datos

Elimina `~/.config/comic-identify/`, `~/.local/share/comic-identify/` y `~/.cache/comic-identify/`, y las
copias de seguridad que hayas creado. Los metadatos `ComicInfo.xml` escritos en tus archivos se pueden deshacer
desde Ajustes antes de borrar los registros. Desinstalar la aplicación no borra esos datos por sí solo.

## Cambios en esta política

Si cambia, se actualizará este documento y la fecha de arriba; el historial está en el repositorio.

## Contacto

Jose Antonio Seguido Doblado · jose.antonio.seguido@gmail.com
