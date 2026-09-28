# Comic Identify

Aplicación de escritorio (GTK 4 + PyGObject, interfaz en español) para gestionar una colección de cómics
digitales (CBR, CBZ y CB7):

- **Identifica** un cómic a partir de su portada o de su título.
- **Normaliza** los nombres de archivos y carpetas según un patrón configurable, con deshacer.
- **Escribe metadatos** `ComicInfo.xml` (el formato que entienden Kavita, Komga y ComicTagger), con deshacer.
- **Lista las series** de tu colección con los números que tienes y los que faltan.

La identificación es local (ZBar, hash perceptual, índice SQLite) y solo consulta la API gratuita de
ComicVine. La IA es opcional: un botón abre tu propia CLI de IA en un terminal (ver más abajo).

## Cómo identifica

El título lo escribes tú: el OCR se descartó porque no lee los logotipos de los cómics (con portadas
reales devolvía texto sin sentido).

1. **Búsqueda mientras escribes** en el índice local de **Grand Comics Database (GCD)** (ediciones en
   español, España primero), por título y número. Es local: sin red ni límites.
2. **Tu colección**: compara la portada con un índice local de las primeras páginas de tus CBZ/CBR/CB7
   y te dice qué archivo es, sin red.
3. **Código de barras** (`zbarimg`): coincidencia exacta en GCD y número de ejemplar del complemento.
4. **ComicVine** (con Enter): busca series y ejemplares (mejor para ediciones americanas) y ordena
   sus portadas por parecido visual (dHash de 256 bits, tolerante a escala, compresión y márgenes).
5. **Ficha en un panel a la derecha** al hacer clic en una sugerencia: de GCD, con número abre el
   ejemplar y sin número la galería de portadas de la serie; de ComicVine, una ficha con la portada grande,
   el título, la editorial y la fecha. «Abrir en el navegador» está en la cabecera del panel.

Ningún método automático acierta al 100 %: el resultado es una lista de candidatos para que elijas.

Además del título y el número puedes acotar con **Editorial / distribuidor** (en GCD también casa con el
sello: «Forum», «Panini»…) y **Año**. La búsqueda en GCD es al vuelo, mientras escribes; la de ComicVine, con
el botón **Buscar en ComicVine** (o Enter), porque consume peticiones de su API. Con número de ejemplar puede
tardar varios segundos (compara la portada de cada serie candidata); mientras tanto se ve una barra de progreso
y el estado dice qué serie se está comparando.

## Ver el cómic abierto

- **Abrir…** (o pegar con Ctrl+V un archivo copiado en el gestor de archivos, o arrastrarlo) abre un CBR/CBZ/CB7 (se usa su primera imagen como portada) o
  una imagen suelta.
- **Páginas:** las flechas bajo la portada (primera, anterior, siguiente, última) permiten mirar el resto de
  páginas, por ejemplo la contraportada. La búsqueda sigue usando la portada.
- **Ampliar:** doble clic en la página a la vista la abre en una ventana grande (flechas, teclado ← → Inicio Fin Esc y
  «Tamaño real», para leer la letra pequeña).
- **ComicInfo.xml:** debajo de las flechas se muestran los metadatos del archivo abierto (o que no tiene), y se
  actualizan solos al escribir o deshacer metadatos.
- **Extraer portada…:** guarda la primera página como imagen junto al archivo, con su mismo nombre y sin
  recodificarla. Sirve, por ejemplo, para tener la portada como archivo aparte al catalogar en GCstar u otro
  programa. No sobrescribe una imagen que ya exista con ese nombre.

## Organizar la colección

**Normalizar nombre…** renombra el cómic abierto según `Estructura.md`
(`Título Volumen X 🇺🇸/🇪🇸 [años del contenido] (años de la edición) - Sello - Editorial`). El formulario propone
los valores desde la sugerencia elegida y tú los corriges; el patrón es configurable con `{nombre}`, `{volumen}`,
`{bandera}`, `{contenido}`, `{edicion}`, `{sello}`, `{editorial}` y `{numero}`. Sello y editorial son cada uno un
tramo independiente del patrón: si falta alguno de los dos, se omite entero sin dejar guiones sueltos. El año real
del contenido en ediciones
españolas hay que ponerlo a mano o buscarlo con el botón **Buscar en ComicVine…** del formulario (título original en inglés
+ números americanos que recoge la edición → fechas de portada); si no se conoce, se deja vacío y el nombre
lleva solo los años de la edición.

**Normalizar carpeta…** (la carpeta es la serie): elige antes una serie de GCD en los resultados, pulsa el botón y
elige la carpeta. Se propone el nombre de la carpeta con los datos de la serie (nombre, bandera, años de la
edición, sello) y los archivos de dentro se llaman como la carpeta más ` #01`, ` #02`… con el número que ya traen
sus nombres (mínimo dos cifras), sin inventar los que faltan. Vista previa completa antes de aplicar, todo o nada, y
un solo deshacer para todo el lote.

Cada renombrado se registra en `~/.local/share/comic-identify/renames.log` y se deshace desde **Ajustes**.

Normalizar y escribir metadatos actúan sobre el archivo original, no sobre una copia, aunque lo hayas abierto pegándolo.

**Metadatos archivo… / Metadatos carpeta…** escriben el `ComicInfo.xml` del cómic abierto o de todos los de una
carpeta: serie, volumen, editorial, sello, año, total, idioma, web, notas, los créditos (guion, lápiz, tinta, color,
rotulación, portada), la categoría que tú eliges y, por archivo, el número, el título y el resumen del ejemplar. Se
rellena con lo que ya tienen los archivos, la serie de GCD y el nombre de la carpeta. Cada escritura se verifica en
una copia antes de sustituir el original, se conservan los campos que no están en el formulario (como las páginas) y
se puede deshacer por lotes desde **Ajustes** (`~/.local/share/comic-identify/metadata.log`). Funciona en CBZ, RAR
(4 y 5) y 7-Zip; para escribir en RAR hace falta el programa `rar` (no libre).

**Series de la colección** (pestaña Mi colección): tras indexar, lista las series con los números que tienes y los que
faltan. Necesita el «Total de números» en los metadatos para saber cuántos faltan al final; sin él solo detecta
huecos entre los que hay. Marca los archivos aislados que parecen de otra serie.

**Transferir a GCstar…** añade el cómic abierto a una colección de [GCstar](https://www.gcstar.org/) sin tocar el
resto de su archivo `.gcs`: solo inserta el elemento nuevo, con los créditos, la editorial, el año, las páginas y la
ruta del archivo, más los campos propios de GCstar (tipo, categoría, formato, colección), con un desplegable que
sugiere lo que ya usas en esa colección; «Categoría» se prerrellena sola con la que ya tenga el archivo, y «Tipo»
con «Europeo», «Americano» o «Manga» según bajo cuál de tus carpetas de «Mi colección» (`EUROPA`, `USA`, `JAPÓN`)
esté el cómic (solo mira el nombre de esas carpetas, no en qué disco estén). También copia la portada y la
contraportada a una carpeta `comics` propia dentro de la del `.gcs` (para compartirla con otras colecciones de
GCstar sin mezclar sus imágenes), con la misma estructura de subcarpetas y el mismo nombre que ya uses (`<nombre>
- Portada.jpg` / `- Trasera.jpg`), siempre que el cómic esté bajo una carpeta configurada en «Mi colección» (si
no, se transfiere sin portada). Se niega a escribir si detecta GCstar abierto, y se puede deshacer por lotes
desde **Ajustes** (`~/.local/share/comic-identify/gcstar.log`); el deshacer no toca una imagen que haya cambiado
desde entonces. La
ruta al `.gcs` se configura una vez en Ajustes.

## Universo Marvel

[fichas.universomarvel.com](https://fichas.universomarvel.com/) es el catálogo más completo de las ediciones españolas de
Marvel (Forum/Planeta, Panini, Vértice…), con fecha, precio, páginas, créditos y el ejemplar USA original de cada número.
No tiene API ni volcado y es una web personal, así que la aplicación **no la rastrea**:

1. En **Ajustes**, «Descargar el índice de Universo Marvel» baja solo las páginas de índice de Forum/Planeta, Panini y
   Vértice (tres peticiones con pausa entre ellas, identificándose como `comic-identify`) y crea
   `~/.local/share/comic-identify/universomarvel.db`. Con él, las series salen entre las sugerencias al escribir el
   título (sin tildes ni mayúsculas, «spider man» encuentra «Spiderman»).
2. Al elegir una serie **con el número escrito**, se consulta solo la ficha de ese ejemplar (una o dos peticiones,
   una sola vez: después sale de la base local) y aparece como candidato con su fecha, páginas, precio y formato; su
   página se ve en el panel de la derecha. Un especial suelto no necesita número.
3. Con ese candidato elegido, **Normalizar nombre** parte de sus datos (nombre, volumen, 🇪🇸, año de la edición, sello y
   editorial) y **Metadatos archivo** precarga año, mes, editorial, sello, la web de su ficha y los créditos de la edición
   (rotulación, traducción, portada); con un solo archivo, también el título del cómic y el código de barras. Las
   páginas (`PageCount`) siempre se cuentan en el propio archivo, con o sin ficha. El contenido original lo sigues
   indicando tú.
   Con un solo archivo, los créditos de guion, lápiz, tinta y color se toman de las fichas USA de los originales
   que recoge el ejemplar (solo de las historias que enlazan a tu ficha española; la rotulación y la traducción
   son las de la española), una petición por original la primera vez y después desde la base local.
   La **sinopsis** de las historias USA (si la ficha del original la trae) se precarga en el Resumen del archivo.
   Mientras se consulta la web, una barra pulsante bajo el estado indica que está trabajando.
   Las Notas llevan además un desglose «Créditos por historia (USA)» (quién hizo qué en cada historia, ya que los campos
   solo admiten una lista por rol).
   Con un cómic abierto, la ficha elegida muestra el **parecido de su portada con la tuya** (el mismo porcentaje que
   en ComicVine) y su miniatura.
   Las Notas llevan, debajo de «Contenido original», los ejemplares USA que recoge la edición (con el enlace a su ficha)
   y los comentarios de la edición; pasan al comentario de GCstar al transferir.
4. En **Transferir a GCstar…**, «Coste» e «ISBN» vienen rellenos con la ficha elegida (el precio en euros: las
   pesetas se convierten a 166,386; el precio no existe en ComicInfo.xml, así que hay que tener la ficha elegida al
   transferir). Un código de barras que no sea un ISBN no se pone en ese campo.

La base guarda de cada ficha sus campos ya leídos y el HTML original comprimido, así que si mejora el lector se
vuelve a leer sin volver a pedir nada a la web. Volver a descargar el índice no borra las fichas.

## Copias de seguridad

En **Ajustes** se elige una carpeta para las copias. Cada copia es un `.zip` con los índices (colección y GCD), los
ajustes y los registros de deshacer, más un manifiesto con el SHA-256 de cada archivo; las bases SQLite se copian con la
API de copia de SQLite (coherentes aunque estén en uso). Se hace una **automática al cerrar** la aplicación (solo si
algo ha cambiado desde la última; se conservan las N últimas, 10 por defecto), y **Copiar ahora** hace una manual (las
manuales nunca se borran solas). **Restaurar una copia…** lista las copias por fecha; antes de sustituir nada
comprueba los SHA-256 y las bases, y guarda el estado actual como copia «antes de restaurar». Ojo: el zip incluye la
clave de ComicVine (se crea legible solo por ti). El `.gcs` de GCstar y tus cómics no forman parte de la copia.

## Webs, asistente de IA y órdenes

Bajo el campo del título, el desplegable **Buscar en otras webs** reúne accesos directos a webs de cómic en español,
agrupadas en *Generalistas* (Tebeosfera, Whakoom, Norma, Norma Comics, Panini, Zona Negativa), *Marvel* (Universo
Marvel) y *DC* (DC Comics, DC Database), y se repliega al elegir una. **Todas**, arriba del todo, abre las nueve, cada
una en su pestaña del navegador. Abren en tu navegador la búsqueda con el título, el número y, si la casilla está marcada, la editorial y
el año: la aplicación no rastrea esas webs, y de hecho algunas lo prohíben en su `robots.txt` (Whakoom y los
buscadores de Panini y DC).

Los iconos de las webs (desplegable y créditos de Ajustes) se descargan la primera vez, como haría un navegador, y se
guardan en `~/.cache/comic-identify/icons`; no se incluyen en el paquete porque son marcas de sus webs. Se pueden
borrar sin problema. Si una web no entrega su icono, se pide al servicio de favicons de Google (solo se le envía el
nombre del dominio); si tampoco lo tiene, se muestra uno genérico.

Para los cómics que ninguna fuente reconoce, el botón **Preguntar a la IA** abre, en el panel derecho, un terminal
embebido (con la tipografía Ubuntu Sans Mono) con tu propia CLI de IA y un mensaje que le pide identificar la portada; puede buscar en la web y consultar
el índice local con `comic-identify buscar "título" [número]`. En **Ajustes** se configuran el comando (Claude Code por
defecto; `{prompt}` se sustituye por el mensaje) y el propio mensaje (`{image}` es la portada). Se lanza desde tu shell,
así que encuentra CLIs como `opencode` o `codex` aunque solo estén en el `PATH` de tu `~/.bashrc`. La aplicación no
maneja tus credenciales ni usa ninguna API: inicias sesión tú en la CLI. La primera vez, Claude Code pregunta si
confías en la carpeta de trabajo (`~/.cache/comic-identify/ai`, que solo contiene la portada); tienes que elegir «Yes»
tú. Requiere `gir1.2-vte-3.91`.

Órdenes de texto (no abren la interfaz): `comic-identify --help`, `comic-identify --version` y
`comic-identify buscar "título" [número]`.

## Instalación y ejecución

**Paquete DEB:** descarga el `.deb` de la última [release](https://github.com/seguidodoblado/comic-identify/releases)
e instálalo:

```bash
sudo apt install ./comic-identify_<versión>-1_all.deb
```

El paquete recomienda (y `apt` instala por defecto) `unrar` o `p7zip-full` para leer RAR y 7-Zip,
`gir1.2-webkit-6.0` para las fichas de GCD y `gir1.2-vte-3.91` para el asistente de IA; sugiere `rar` para escribir
metadatos en RAR.

**Entorno de desarrollo.** Dependencias del sistema (Debian/Ubuntu/Mint):

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 python3-pil python3-numpy zbar-tools unrar p7zip-full gir1.2-webkit-6.0 gir1.2-vte-3.91
```

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e '.[dev]'
comic-identify [portada.jpg | cómic.cbz]
```

Para identificar por título necesitas al menos una de estas dos fuentes (o ambas), en la pestaña **Ajustes**; la
identificación por portada contra tu propia colección no necesita ninguna:

- **GCD** (recomendada para ediciones en español): descarga el volcado SQLite de
  <https://www.comics.org/download/> (cuenta gratuita, ~1,8 GB comprimido, ~6,7 GB descomprimido) e
  impórtalo con **Importar volcado de GCD…**. Tarda unos segundos y genera un índice de ~14 MB en
  `~/.local/share/comic-identify/gcd_es.db`; el volcado ya no hace falta después.
  Si actualizas desde una versión anterior, vuelve a importarlo: la app te avisa cuando el índice es antiguo.
- **ComicVine**: clave gratuita en <https://comicvine.gamespot.com/api/>.

La clave de ComicVine se guarda en `~/.config/comic-identify/config.json` (permisos 600).

## Uso

Al hacer clic en una sugerencia de GCD, su ficha de comics.org se abre en un panel a la derecha (requiere
`gir1.2-webkit-6.0`; sin él, se abre en el navegador). Las de ComicVine usan una ficha propia, sin WebKit. Con número
se abre el ejemplar; sin número, la galería de portadas de la serie (GCD la pagina de 50 en 50). Se carga una sola
página por clic y la aplicación no extrae ni guarda ninguna imagen: es una vista de comics.org tal como la ve un
navegador. Como cualquier navegador, WebKit mantiene su caché y sus cookies en `~/.cache/comic-identify/webkit` y
`~/.local/share/comic-identify/webkit`; se pueden borrar sin problema.

- **Identificar**: abre, pega o arrastra un cómic (CBR/CBZ/CB7) o una imagen de portada, busca y elige.
- **Mi colección**: añade carpetas e indexa. Se recorren con subcarpetas y las siguientes veces solo se
  procesan los archivos nuevos o modificados (y se leen sus metadatos). Los `.cbr` se leen con `unrar` o, si no
  está, `7z`. El índice vive en `~/.local/share/comic-identify/library.db`. Si una carpeta configurada no está
  accesible (disco externo desmontado, carpeta vacía), su índice se conserva y se avisa; al quitarla de la lista, sus
  portadas se olvidan al momento. Debajo, la lista de series con sus huecos.
- **Ajustes**: clave de ComicVine, volcado de GCD, comando y mensaje del asistente de IA, deshacer renombrados y
  metadatos, y el botón **Acerca de…**.

## Comprobaciones

```bash
pytest
ruff check .
```

## Construir el paquete DEB

Mismo patrón que `joseflix-request` y `telegraph-writer`:

```bash
./build-deb.sh
sudo apt install ../comic-identify_<versión>-1_all.deb
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
- La lista de series supone que una carpeta es una serie: en carpetas sueltas o de eventos, con varias series
  mezcladas y sin metadatos, no se calculan huecos.

## Datos de terceros

Los datos de GCD son © Grand Comics Database (<https://www.comics.org/>) y se distribuyen bajo
licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). El índice local que genera
la aplicación es una obra derivada y debe conservar esa atribución y licencia si se comparte.

## Licencia

Este proyecto se distribuye bajo la GNU General Public License, versión 3 (ver `LICENSE`).
