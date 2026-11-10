# Política de privacidad / Privacy Policy

## 🇪🇸 Español

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

---

## 🇺🇸 English

Last updated: October 5, 2026.

Comic Identify is a desktop application for personal use. It has no server or account of its own, and its
author does not receive any data from the people who use it.

## What data it handles

- **Your comic collection:** the paths of the folders you choose, file names, covers (to compute their visual
  fingerprint and read the barcode) and the `ComicInfo.xml` metadata that the application writes into your files.
- **Your settings:** folders, naming pattern, AI assistant command, backup folder and, if you set it, your
  ComicVine API key.
- **Undo logs** for renames, metadata and GCstar transfers.

## Where it is stored

Everything stays on your computer, in the user's XDG directories:

- `~/.config/comic-identify/config.json`: settings and ComicVine key (in clear text, protected by 600 permissions).
- `~/.local/share/comic-identify/`: local indexes (collection, Grand Comics Database, Universo Marvel and
  Tebeosfera), undo logs and your own logos.
- `~/.cache/comic-identify/`: downloaded logos and icons, web panel cache and the assistant's working folder.
- Backups, in the folder you choose.

## Who it is shared with

No one, on the application's part. It includes no analytics, telemetry or advertising. The network is only
used when you ask for it, and requests go from your computer to:

- **Grand Comics Database** (comics.org), **Universo Marvel**, **Tebeosfera** and **ComicVine**, to search and
  download records. ComicVine receives your API key and the search text. The others receive the query or the
  record's address.
- The search and shopping websites you open from the application, in the built-in web panel or in your
  browser. Those sites have their own policies; the application blocks Tebeosfera's measurement and
  advertising in the panel, and does not store cookies on disk except comics.org's access cookie, only in memory.
- **The AI assistant is optional and uses your own session.** If you enable it, the application runs the
  command you configure (by default, `claude`) with a message and the path of the cover. What that program
  sends to its own service is governed by its own policy, not this one.

The covers of your files are not sent to any server of the application, which does not exist.

## How to delete your data

Remove `~/.config/comic-identify/`, `~/.local/share/comic-identify/` and `~/.cache/comic-identify/`, and any
backups you created. The `ComicInfo.xml` metadata written into your files can be undone from Settings before
deleting the logs. Uninstalling the application does not delete that data by itself.

## Changes to this policy

If it changes, this document and the date above will be updated; the history is in the repository.

## Contact

Jose Antonio Seguido Doblado · jose.antonio.seguido@gmail.com
