# Comic Identify

Aplicación de escritorio (GTK 4 + PyGObject) que identifica un cómic a partir de su portada.
La identificación es local (ZBar, hash perceptual, índice SQLite) y solo consulta la API gratuita de
ComicVine. La IA es opcional: un botón abre tu propia CLI de IA en un terminal (ver más abajo).

## Cómo identifica

El título lo escribes tú: el OCR se descartó porque no lee los logotipos de los cómics (con portadas
reales devolvía texto sin sentido).

1. **Búsqueda mientras escribes** en el índice local de **Grand Comics Database (GCD)** (ediciones en
   español, España primero), por título y número. Es local: sin red ni límites.
2. **Tu colección**: compara la portada con un índice local de las primeras páginas de tus CBZ/CBR
   y te dice qué archivo es, sin red.
3. **Código de barras** (`zbarimg`): coincidencia exacta en GCD y número de ejemplar del complemento.
4. **ComicVine** (con Enter): busca series y ejemplares (mejor para ediciones americanas) y ordena
   sus portadas por parecido visual (dHash de 256 bits, tolerante a escala, compresión y márgenes).
5. **Ficha en un panel a la derecha** al hacer clic en una sugerencia: de GCD, con número abre el
   ejemplar y sin número la galería de portadas de la serie; de ComicVine, una ficha con la portada grande,
   el título, la editorial y la fecha. «Abrir en el navegador» está en la cabecera del panel.

Ningún método automático acierta al 100 %: el resultado es una lista de candidatos para que elijas.

Los iconos de las webs (botones de búsqueda y créditos de Ajustes) se descargan la primera vez, como
haría un navegador, y se guardan en `~/.cache/comic-identify/icons`; no se incluyen en el paquete porque
son marcas de sus webs. Se pueden borrar sin problema.

Además del título y el número puedes acotar con **Editorial / distribuidor** (en GCD también casa con el
sello: «Forum», «Panini»…) y **Año**. La búsqueda en GCD es al vuelo, mientras escribes; la de ComicVine, con
el botón **Buscar en ComicVine** (o Enter), porque consume peticiones de su API.

**Normalizar carpeta…** (la carpeta es la serie): elige antes una serie de GCD en los resultados, pulsa el botón y
elige la carpeta. Se propone el nombre de la carpeta con los datos de la serie (nombre, bandera, años de la
edición, sello) y los archivos de dentro se llaman como la carpeta más ` #01`, ` #02`… con el número que ya traen sus nombres, sin
inventar los que faltan. Vista previa completa antes de aplicar, todo o nada, y un solo deshacer para todo el
lote.

**Páginas:** con un CBR/CBZ abierto, las flechas bajo la portada (primera, anterior, siguiente, última) permiten mirar
el resto de páginas, por ejemplo la contraportada. La búsqueda sigue usando la portada.

**Metadatos…** escribe el `ComicInfo.xml` de todos los cómics de una carpeta (o del abierto): serie, volumen,
editorial, sello, año, total, idioma, web, notas, la categoría que tú eliges y el número y título de cada archivo. Se
rellena con lo que ya tienen los archivos, la serie de GCD y el nombre de la carpeta. Cada escritura se verifica en una
copia antes de sustituir el original y se puede deshacer por lotes desde Ajustes. Para escribir en RAR hace falta el
programa `rar`.

**Series de la colección** (pestaña Mi colección): tras indexar, lista las series con los números que tienes y los que
faltan. Necesita el «Total de números» en los metadatos para saber cuántos faltan al final; sin él solo detecta
huecos entre los que hay. Marca los archivos aislados que parecen de otra serie.

**Normalizar nombre…** renombra el CBR/CBZ abierto según `Estructura.md`
(`Título Volumen X 🇺🇸/🇪🇸 [años del contenido] (años de la edición) - Sello`). El formulario propone los
valores desde la sugerencia elegida y tú los corriges; el patrón es configurable con `{nombre}`, `{volumen}`,
`{bandera}`, `{contenido}`, `{edicion}`, `{sello}` y `{numero}`. El año real del contenido en ediciones
españolas hay que ponerlo a mano o buscarlo con el botón **Buscar en ComicVine…** del formulario (título original en inglés
+ números americanos que recoge la edición → fechas de portada); si no se conoce, se deja vacío y el nombre
lleva solo los años de la edición. Cada
cambio se registra en `~/.local/share/comic-identify/renames.log` y se deshace desde Ajustes.

Órdenes de texto (no abren la interfaz): `comic-identify --help` y `comic-identify buscar "título" [número]`.

Bajo el campo del título hay accesos directos a otras webs de cómic en español (Tebeosfera, Whakoom,
Norma, Panini, Universo Marvel y Zona Negativa). Abren en tu navegador la búsqueda con el título, el número y, si
la casilla está marcada, la editorial y el año: la aplicación no
rastrea esas webs, y de hecho algunas lo prohíben en su `robots.txt` (Whakoom, el buscador de Panini).

Para los cómics que ninguna fuente reconoce, el botón **Preguntar a la IA** abre, en el panel derecho, un terminal embebido con
tu propia CLI de IA (Claude Code por defecto, configurable en Ajustes) y un mensaje que le pide
identificar la portada; puede buscar en la web y consultar el índice local con
`comic-identify buscar "título" [número]`. La aplicación no maneja tus credenciales ni usa ninguna API:
inicias sesión tú en la CLI. La primera vez, Claude Code pregunta si confías en la carpeta de trabajo
(`~/.cache/comic-identify/ai`, que solo contiene la portada); tienes que elegir «Yes» tú. Requiere
`gir1.2-vte-3.91`.

## Instalación y ejecución

Dependencias del sistema (Debian/Ubuntu/Mint):

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 python3-pil python3-numpy zbar-tools unrar gir1.2-webkit-6.0 gir1.2-vte-3.91
```

Entorno de desarrollo:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e '.[dev]'
comic-identify [portada.jpg]
```

Necesitas al menos una de estas dos fuentes (o ambas), en la pestaña **Ajustes**:

- **GCD** (recomendada para ediciones en español): descarga el volcado SQLite de
  <https://www.comics.org/download/> (cuenta gratuita, ~1,8 GB comprimido, ~6,7 GB descomprimido) e
  impórtalo con **Importar volcado de GCD…**. Tarda unos segundos y genera un índice de ~14 MB en
  `~/.local/share/comic-identify/gcd_es.db`; el volcado ya no hace falta después.
  Si actualizas desde una versión anterior, vuelve a importarlo: la app te avisa cuando el índice es antiguo.
- **ComicVine**: clave gratuita en <https://comicvine.gamespot.com/api/>.

La clave de ComicVine se guarda en `~/.config/comic-identify/config.json` (permisos 600).

## Uso

Al hacer clic en una sugerencia de GCD, su ficha de comics.org se abre en un panel a la derecha (requiere
`gir1.2-webkit-6.0`; sin él, se abre en el navegador). Las de ComicVine usan una ficha propia, sin WebKit. Con número se abre el ejemplar; sin número,
la galería de portadas de la serie (GCD la pagina de 50 en 50). Se carga una sola página por clic y la
aplicación no extrae ni guarda ninguna imagen: es una vista de comics.org tal como la ve un navegador.
Como cualquier navegador, WebKit mantiene su caché y sus cookies en `~/.cache/comic-identify/webkit` y
`~/.local/share/comic-identify/webkit`; se pueden borrar sin problema.

- **Identificar**: abre, pega (Ctrl+V) o arrastra una imagen de portada, o directamente un archivo CBR/CBZ (se usa su primera imagen).
- **Mi colección**: añade carpetas e indexa. Se recorren con subcarpetas y las siguientes veces solo se
  procesan los archivos nuevos o modificados. Los `.cbr` se leen con `unrar` o, si no está, `7z`.
  El índice vive en `~/.local/share/comic-identify/library.db`.
  Si una carpeta configurada no está accesible (disco externo desmontado, carpeta vacía), su índice se
  conserva y se avisa; al quitarla de la lista, sus portadas se olvidan al momento.

## Comprobaciones

```bash
pytest
ruff check .
```

## Construir e instalar el paquete DEB

Mismo patrón que `joseflix-request` y `telegraph-writer`:

```bash
./build-deb.sh
sudo apt install ../comic-identify_0.1.0-1_all.deb
```

## Limitaciones conocidas

- Los candidatos de GCD se buscan solo por texto y código de barras: el volcado no incluye portadas, así
  que no se comparan visualmente (la interfaz lo indica). Solo el índice de tu colección y ComicVine
  comparan imagen.
- La cobertura de GCD es desigual: Marvel y DC de Planeta, Zinco y Panini hasta ~2011 están bien
  representados, pero lo reciente de Panini y ECC es parcial. Solo un ~2 % de los números españoles
  tiene código de barras registrado.

- El umbral de coincidencia (`MATCH_THRESHOLD` en `identify.py`) está calibrado solo con portadas
  sintéticas; conviene ajustarlo con portadas reales.
- La lectura del código de barras depende de `zbarimg` y de que el código sea legible en la imagen.
- ComicVine limita las peticiones; cada identificación hace unas pocas consultas.

## Datos de terceros

Los datos de GCD son © Grand Comics Database (<https://www.comics.org/>) y se distribuyen bajo
licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). El índice local que genera
la aplicación es una obra derivada y debe conservar esa atribución y licencia si se comparte.

## Licencia

Este proyecto se distribuye bajo los términos indicados en `LICENSE`.
