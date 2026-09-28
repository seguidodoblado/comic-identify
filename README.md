# Comic Identify

Aplicación de escritorio (GTK 4 + PyGObject, interfaz en español) para gestionar una colección de cómics
digitales (CBR, CBZ y CB7):

- **Identifica** un cómic a partir de su portada o de su título, con Grand Comics Database (GCD), el catálogo de
  ediciones españolas de Marvel de [Universo Marvel](https://fichas.universomarvel.com/), el de toda la historieta
  editada en España de [Tebeosfera](https://www.tebeosfera.com/), ComicVine y tu propia colección.
- **Normaliza** los nombres de archivos y carpetas según un patrón configurable, con deshacer.
- **Escribe metadatos** `ComicInfo.xml` (el formato que entienden Kavita, Komga y ComicTagger), con deshacer y con datos
  de las fichas de Universo Marvel y de Tebeosfera (créditos, fecha, géneros, ISBN…).
- **Lista las series** de tu colección con los números que tienes y los que faltan.
- **Transfiere** el cómic catalogado a tu colección de [GCstar](https://www.gcstar.org/), con su portada.
- **Copias de seguridad** verificadas de sus índices y ajustes, con restauración.
- **Busca dónde comprar** el ejemplar (Panini, segunda mano, tiendas) y abre otras webs de cómic.

La identificación es local (ZBar, hash perceptual, índices SQLite); consulta la API gratuita de ComicVine y, solo cuando
eliges un resultado, las fichas de Universo Marvel y de Tebeosfera (una página cada vez, guardada después en local). La IA es opcional:
un botón abre tu propia CLI de IA en un terminal (ver más abajo).

## Cómo identifica

El título lo escribes tú: el OCR se descartó porque no lee los logotipos de los cómics (con portadas
reales devolvía texto sin sentido).

1. **Búsqueda mientras escribes** en el índice local de **Grand Comics Database (GCD)** (ediciones en
   español, España primero), por título y número, en el de **Universo Marvel** (series de Forum/Planeta, Panini y
   Vértice) y en el de **Tebeosfera** (todas las colecciones, de cualquier editorial). Es local: sin red ni límites.
2. **Tu colección**: compara la portada con un índice local de las primeras páginas de tus CBZ/CBR/CB7
   y te dice qué archivo es, sin red.
3. **Código de barras** (`zbarimg`): coincidencia exacta en GCD y número de ejemplar del complemento.
4. **ComicVine** (con Enter): busca series y ejemplares (mejor para ediciones americanas) y ordena
   sus portadas por parecido visual (dHash de 256 bits, tolerante a escala, compresión y márgenes).
5. **Ficha en un panel a la derecha** al hacer clic en una sugerencia: de GCD, con número abre el
   ejemplar y sin número la galería de portadas de la serie; de ComicVine, una ficha con la portada grande,
   el título, la editorial y la fecha; de Universo Marvel y de Tebeosfera, la página de la serie o del ejemplar (ver más
   abajo).
   «Abrir en el navegador» está en la cabecera del panel. El panel se adapta al ancho de la pantalla (mínimo 420 px; el
   terminal del asistente pide 760) y la ventana no crece más que la pantalla ni cambia de tamaño si está maximizada.

Ningún método automático acierta al 100 %: el resultado es una lista de candidatos para que elijas. Al escribir,
salen primero los de **tu colección**, luego los de **Tebeosfera**, los de **Universo Marvel** y los de **GCD**; con
una portada abierta, primero tu colección y el código de barras exacto y después, por parecido de portada, el resto. Cada uno lleva su
fuente (GCD en morado, Universo Marvel en rojo, Tebeosfera en naranja y ComicVine en verde, con el icono de su web) y, cuando la editorial es una de las conocidas (Forum, Panini, Vértice, Planeta DeAgostini, ECC, Zinco, Norma o Bruguera), su
logotipo.

Además del título y el número puedes acotar con **Editorial / distribuidor** (en GCD también casa con el
sello: «Forum», «Panini»…) y **Año**. La búsqueda en GCD es al vuelo, mientras escribes; la de ComicVine, con
el botón **Buscar en ComicVine** (o Enter), porque consume peticiones de su API. Con número de ejemplar puede
tardar varios segundos (compara la portada de cada serie candidata); mientras tanto se ve una barra de progreso
y el estado dice qué serie se está comparando.

## Ver el cómic abierto

- **Abrir…** (o pegar con Ctrl+V un archivo copiado en el gestor de archivos, o arrastrarlo) abre un CBR/CBZ/CB7 (se usa su primera imagen como portada) o
  una imagen suelta. Abrir un elemento nuevo cierra el panel derecho si estaba abierto con la ficha o la sesión de IA del anterior.
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
del contenido en ediciones españolas hay que ponerlo a mano o buscarlo con el botón **Buscar en ComicVine…** del
formulario (título original en inglés + números americanos que recoge la edición → fechas de portada); si no se
conoce, se deja vacío y el nombre lleva solo los años de la edición.

**Normalizar carpeta…** (la carpeta es la serie): elige antes una serie de GCD en los resultados, pulsa el botón y
elige la carpeta. Se propone el nombre de la carpeta con los datos de la serie (nombre, bandera, años de la
edición, sello) y los archivos de dentro se llaman como la carpeta más ` #01`, ` #02`… con el número que ya traen
sus nombres (mínimo dos cifras), sin inventar los que faltan. Vista previa completa antes de aplicar, todo o nada, y
un solo deshacer para todo el lote.

Cada renombrado se registra en `~/.local/share/comic-identify/renames.log` y se deshace desde **Ajustes**.

Normalizar y escribir metadatos actúan sobre el archivo original, no sobre una copia, aunque lo hayas abierto pegándolo.

**Créditos de GCD.** Si eliges un resultado de GCD **con número** (no una serie), «Metadatos archivo…» precarga lo que
GCD sabe de ese número: guion, lápiz, tinta, color, rotulación, edición y autor de la portada (los mismos que muestra su
web, del modelo nuevo de «creadores» del volcado), el género (en español si se conoce) y los personajes, la fecha, la
web del número, el código de barras y la sinopsis si la hay. Los traductores (que GCD anota como «guion» con la nota
«traducción») van a Traducción, no a Guion. Una historia sin créditos propios hereda los de la historia original de la
que es reimpresión. Con varias historias se añade en las Notas «Créditos por historia (GCD)». Como los créditos son de un
solo ejemplar, solo se ofrecen al etiquetar un archivo suelto; y hace falta un índice de GCD reciente: si el tuyo es
anterior (Ajustes lo avisa), vuelve a importar el volcado. «Transferir a GCstar…» toma de ahí el coste cuando GCD lo da
en euros o en pesetas (convertidas), y el ISBN.

**Metadatos archivo… / Metadatos carpeta…** escriben el `ComicInfo.xml` del cómic abierto o de todos los de una
carpeta: serie, volumen, editorial, sello, año (y, opcionales, mes y día), total, idioma, formato, género, personajes,
web, notas (varias líneas), los créditos (guion, lápiz, tinta, color, rotulación, traducción, edición, portada), la categoría que tú eliges y, por
archivo, el número, el título y el resumen del ejemplar. El número de páginas (`PageCount`) se cuenta siempre en el
propio archivo. Se rellena con lo que ya tienen los archivos, la serie de GCD, la ficha de Universo Marvel elegida y el
nombre de la carpeta; lo que el archivo ya tiene no se pisa. Cada escritura se verifica en una copia antes de sustituir el
original, se conservan los campos que no están en el formulario (como las páginas) y se puede deshacer por lotes desde
**Ajustes** (`~/.local/share/comic-identify/metadata.log`). Funciona en CBZ, RAR (4 y 5) y 7-Zip; para escribir en RAR
hace falta el programa `rar` (no libre).

**Series de la colección** (pestaña Mi colección): tras indexar, lista las series con los números que tienes y los que
faltan. Necesita el «Total de números» en los metadatos para saber cuántos faltan al final; sin él solo detecta
huecos entre los que hay. Marca los archivos aislados que parecen de otra serie.

**Transferir a GCstar…** añade el cómic abierto a una colección de [GCstar](https://www.gcstar.org/) sin tocar el
resto de su archivo `.gcs`: solo inserta el elemento nuevo. Lleva el nombre y la serie, el número, los créditos (guion,
lápiz, tinta, color, rotulación y «Cover Artist»), «Publicado por» como «Editorial - Sello» (GCstar no tiene campo de
sello), la fecha de publicación (con día y mes si se conocen), la sinopsis, las notas como comentario (con «Traducción: …» y «Edición: …» al final si hay dato, ya que GCstar no tiene campos para ellas), la etiqueta «Color» o «B&N» (según el `BlackAndWhite` del archivo, si lo tiene), la web, el ISBN,
las páginas contadas en el archivo y la ruta del archivo. Además, los campos propios de GCstar (tipo, categoría,
formato, colección, coste e ISBN), con un desplegable que sugiere lo que ya usas en esa colección: «Categoría» y
«Formato» se prerrellenan con los del archivo; «Tipo» con «Europeo», «Americano» o «Manga» según bajo cuál de tus
carpetas de «Mi colección» (`EUROPA`, `USA`, `JAPÓN`) esté el cómic (solo mira el nombre de esas carpetas, no en qué
disco estén); «Coste» e «ISBN» con los de la ficha de Universo Marvel elegida (ver más abajo). También copia la portada
y la contraportada a una carpeta `comics` propia dentro de la del `.gcs` (para compartirla con otras colecciones de
GCstar sin mezclar sus imágenes), con la misma estructura de subcarpetas y el mismo nombre que ya uses (`<nombre>
- Portada.jpg` / `- Trasera.jpg`), siempre que el cómic esté bajo una carpeta configurada en «Mi colección» (si
no, se transfiere sin portada). Se niega a escribir si detecta GCstar abierto, y se puede deshacer por lotes
desde **Ajustes** (`~/.local/share/comic-identify/gcstar.log`); el deshacer no toca una imagen que haya cambiado
desde entonces. La ruta al `.gcs` se configura una vez en Ajustes.

## Universo Marvel

[fichas.universomarvel.com](https://fichas.universomarvel.com/) es el catálogo más completo de las ediciones españolas de
Marvel (hoy la aplicación usa Forum/Planeta, Panini y Vértice), con fecha, precio, páginas, formato, créditos, comentarios
y el ejemplar USA original de cada número. No tiene API ni volcado y es una web personal, así que la aplicación **no la
rastrea**: descarga una página cada vez, con pausa entre peticiones y el nombre `comic-identify` como identificación.

**Cómo se usa**

1. En **Ajustes**, «Descargar el índice de Universo Marvel» baja solo las tres páginas de índice y crea
   `~/.local/share/comic-identify/universomarvel.db`. Con él, las series salen entre las sugerencias al escribir el
   título (sin tildes ni mayúsculas: «spider man» encuentra «Spiderman»).
2. Al elegir una serie **con el número escrito** se consulta la ficha de ese ejemplar (y su portada): una o dos peticiones,
   una sola vez; después sale de la base local. Aparece como candidato con fecha, páginas, precio y formato, con su
   miniatura y, si hay un cómic abierto, el **parecido de su portada con la tuya** (el mismo porcentaje que en
   ComicVine). Un especial suelto no necesita número. Mientras se descarga, una barra pulsante lo indica. Si la serie
   lista sus fichas por título y no por número (p. ej. Amalgam), se ofrecen esas fichas en la lista para elegir una.
   También puedes **navegar por la web dentro del panel**: al llegar a la ficha de un ejemplar aparece **Usar esta ficha**,
   que la convierte en el resultado elegido, con todos sus datos.
3. Con ese candidato elegido, **Normalizar nombre** parte de sus datos (nombre, volumen, 🇪🇸, año de la edición, sello y
   editorial) y **Metadatos archivo** precarga lo que la ficha sabe (ver abajo).
4. En **Transferir a GCstar…**, «Coste» e «ISBN» vienen rellenos con la ficha elegida: el precio en euros (las pesetas se
   convierten a 166,386) y el ISBN si lo trae; el precio no existe en ComicInfo.xml, así que la ficha debe estar elegida
   al transferir. Un código de barras que no sea un ISBN no se pone en ese campo.

**Qué pasa a los metadatos** (con un solo archivo; mes, créditos de la edición y demás son de un ejemplar y no se ofrecen
al etiquetar una carpeta entera):

- De la ficha española: año, mes (la ficha lo escribe en letra: «Febrero 1997»), editorial, sello, idioma, formato (solo si
  la ficha lo dice), web de la ficha, rotulación, traducción, autores de la portada, título del cómic, código de barras
  (`GTIN`, o el ISBN si lo hay) y **Blanco y negro** (`BlackAndWhite`: «Yes» si la ficha dice blanco y negro, «No» si dice
  color; el diálogo no lo muestra, se escribe al aplicar; con «Bicolor» u otra cosa, se deja como esté).
- De las fichas USA de los originales que recoge el ejemplar: guion, lápiz, tinta y color (el argumento cuenta como guion)
  y la sinopsis, que va al Resumen. De cada original solo se usan las historias que enlazan a tu ficha española; si no se
  puede saber cuáles, se usan todas y el diálogo avisa («Revisa»), igual que si algún enlace de la web está roto.
  La rotulación y la traducción son siempre las de la ficha española.
- En las **Notas**, bajo «Contenido original»: el «Contenido USA» (cada original con el enlace a su ficha), un
  desglose «Créditos por historia (USA)» (quién hizo qué en cada historia, ya que los campos solo admiten una lista por
  rol) y los comentarios de la edición. De ahí pasan al comentario de GCstar.
- El contenido original (los años) lo sigues indicando tú.

La base guarda de cada ficha sus campos ya leídos y el HTML original comprimido, así que si mejora el lector se vuelve a
leer sin volver a pedir nada a la web; las portadas se guardan reducidas (500 px). Volver a descargar el índice no borra
las fichas.

## Tebeosfera

[Tebeosfera](https://www.tebeosfera.com/) es el gran catálogo de la historieta editada en España, de todas las editoriales y
épocas (Panini, ECC, Norma, Planeta, Zinco, Forum, Vértice, Bruguera…). Lo mantiene una asociación cultural y no tiene API
ni volcado, así que la aplicación **no la rastrea**: su `robots.txt` solo veta `/adminpanel/` y anuncia sus sitemaps
públicos, y de ahí sale el índice; cada ficha se pide solo cuando eliges un ejemplar. Todas las peticiones llevan pausa
(1,5 s), piden la página comprimida y se identifican como `comic-identify`.

Funciona igual que Universo Marvel:

1. En **Ajustes**, «Descargar el índice de Tebeosfera» baja los sitemaps (unas 13 peticiones, unos 20 segundos, ~13 MB en
   `~/.local/share/comic-identify/tebeosfera.db`): unas 44.000 colecciones y sus ~490.000 números. Las colecciones salen entre
   las sugerencias al escribir el título (con un chip naranja y el icono de la web), sin tildes ni mayúsculas.
2. Al elegir una colección **con el número escrito** se consulta la ficha de ese ejemplar y su portada (una vez; luego sale
   de la base local): fecha, páginas, precio, formato, créditos y el **parecido de su portada con la tuya**. Un número único
   (un libro, un especial) no necesita número. Si el número no existe, se ofrecen los más cercanos. También puedes
   **navegar por la web en el panel** y pulsar **Usar esta ficha** al llegar a la de un ejemplar.
3. **Metadatos archivo** (con un solo archivo) precarga de la ficha: año, mes y día, total de la colección, editorial, sello
   (si lo hay), idioma, formato, web, todos los créditos (guion, lápiz, tinta, color, rotulación, portada, traducción,
   edición), **género**, «sagas» como personajes, título del número, código de barras (ISBN o EAN), **Blanco y negro** (según
   el interior) y, en las Notas, los datos de la edición que no tienen campo (origen, distribución, tamaño, color, impresión,
   ISSN, depósito legal), las ediciones relacionadas y el texto de la ficha.
4. **Transferir a GCstar…** usa el mismo coste (las pesetas se convierten) e ISBN de la ficha elegida.

Tebeosfera escribe títulos y nombres en MAYÚSCULAS: se pasan a mayúscula inicial (conservando siglas y cifras romanas), que es
lo único que se puede hacer sin perder información; los que ya traen minúsculas se respetan. En la lista, las colecciones
salen con el nombre que da su dirección (sin tildes) hasta que consultas alguna de sus fichas. Las imágenes son de sus
titulares; la base local es para tu uso personal, no la redistribuyas.

## Copias de seguridad

En **Ajustes** se elige una carpeta para las copias. Cada copia es un `.zip` con los índices (colección, GCD, Universo Marvel y Tebeosfera), los
ajustes y los registros de deshacer, más un manifiesto con el SHA-256 de cada archivo; las bases SQLite se copian con la
API de copia de SQLite (coherentes aunque estén en uso). Se hace una **automática al cerrar** la aplicación (solo si
algo ha cambiado desde la última; se conservan las N últimas, 10 por defecto), y **Copiar ahora** hace una manual (las
manuales nunca se borran solas). **Restaurar una copia…** lista las copias por fecha; antes de sustituir nada
comprueba los SHA-256 y las bases, y guarda el estado actual como copia «antes de restaurar». Ojo: el zip incluye la
clave de ComicVine (se crea legible solo por ti). El `.gcs` de GCstar y tus cómics no forman parte de la copia.

## Tema claro y oscuro

En **Ajustes**, «Claro» y «Oscuro» cambian al tema GTK hermano del que tenga tu sistema, conservando el acento
(`Mint-Y-Aqua` ↔ `Mint-Y-Dark-Aqua`, `Adwaita` ↔ `Adwaita-dark`); en oscuro se usan los iconos simbólicos y en claro los de
color de tu tema de iconos. La elección se guarda en `config.json` (`dark_mode`) y se aplica al arrancar; mientras no elijas,
se sigue el tema del sistema. Cambiarlo reinicia la aplicación (una ventana ya presentada no se repinta en Cinnamon/Mint) y
conserva el cómic abierto, lo escrito en los campos y la pestaña; no se puede cambiar durante una indexación.

## Webs, asistente de IA y órdenes

Bajo el campo del título, el desplegable **Buscar en otras webs** reúne accesos directos a webs de cómic en español,
agrupadas en *Generalistas* (Tebeosfera, Whakoom, Norma, Norma Comics, Panini, Zona Negativa), *Marvel* (Universo
Marvel) y *DC* (DC Comics, DC Database), y se repliega al elegir una. **Todas**, arriba del todo, abre las nueve, cada
una en su pestaña del navegador. Abren en tu navegador la búsqueda con el título, el número y, si la casilla está
marcada, la editorial y el año: la aplicación no rastrea esas webs, y de hecho algunas lo prohíben en su `robots.txt`
(Whakoom y los buscadores de Panini y DC).

El menú **Comprar**, a su lado, abre la búsqueda del ejemplar (con el resultado elegido, o lo escrito si no hay ninguno) en
todas las tiendas a la vez con **Todas** (arriba del todo, cada una en su pestaña) o en una sola: Panini, en webs de segunda mano (Todocolección, eBay.es, Wallapop, Milanuncios, Iberlibro) y en tiendas (Amazon.es, Casa
del Libro). Forum/Planeta y Vértice ya no publican, así que sus números solo aparecen de segunda mano. Sin enlaces de
afiliado y sin rastrear nada: es tu navegador quien carga la búsqueda.

Los resultados de Universo Marvel y de GCD llevan, a la derecha, el logotipo de la editorial cuando es Forum (por el sello), Panini,
Vértice, Planeta DeAgostini, ECC, Zinco, Norma o Bruguera; se descargan una vez de la web de fichas a `~/.cache/comic-identify/logos` (no van en el paquete) y se pueden
borrar sin problema.

Las editoriales sin logotipo propio (la mayoría de las latinoamericanas y otras muchas españolas) llevan en su lugar una
etiqueta con su nombre, así que ninguna fila de GCD queda sin marca. Para ponerles su logotipo, guarda un archivo `.png`,
`.jpg` o `.svg` (de cualquier tamaño: se reduce al hueco de la fila) con el nombre que aparece en la ayuda de la etiqueta (p. ej. `ediciones-b.png`) en
`~/.local/share/comic-identify/logos`; también sirve para cambiar los que se descargan (`forum.png`, `ecc.png`…).

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
`gir1.2-webkit-6.0` para las fichas de GCD y de Universo Marvel y `gir1.2-vte-3.91` para el asistente de IA; sugiere `rar` para escribir
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
  impórtalo con **Importar volcado de GCD…**. Tarda unos segundos y genera un índice de ~40 MB (con las historias y los créditos de cada número) en
  `~/.local/share/comic-identify/gcd_es.db`; el volcado ya no hace falta después.
  Si actualizas desde una versión anterior, vuelve a importarlo: la app te avisa cuando el índice es antiguo.
- **ComicVine**: clave gratuita en <https://comicvine.gamespot.com/api/>.

La clave de ComicVine se guarda en `~/.config/comic-identify/config.json` (permisos 600).

## Uso

Al hacer clic en una sugerencia de GCD, su ficha de comics.org se abre en un panel a la derecha (requiere
`gir1.2-webkit-6.0`; sin él, se abre en el navegador); las de Universo Marvel abren de la misma forma su página. Las de ComicVine usan una ficha propia, sin WebKit. Con número
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
- **Ajustes**: tema claro u oscuro (se recuerda; cambiarlo reinicia la aplicación con lo que tenías abierto), clave de ComicVine, volcado de GCD, índice de Universo Marvel, comando y mensaje del asistente de IA,
  deshacer renombrados, metadatos y transferencias a GCstar, ruta del `.gcs`, copias de seguridad y restauración, y el
  botón **Acerca de…**.

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
- Los créditos de GCD dependen de lo que hayan anotado sus colaboradores: en el índice en español, ~87 % de los números tiene
  algún crédito, pero muchos solo el de portada o el de la traducción. Los géneros se traducen al español solo los más
  comunes, las sinopsis (solo ~7 % de las historias) casi siempre están en inglés, y el precio solo se convierte si
  GCD lo da en euros o pesetas.
- El umbral de coincidencia (`MATCH_THRESHOLD` en `identify.py`) está calibrado solo con portadas
  sintéticas; conviene ajustarlo con portadas reales.
- La lectura del código de barras depende de `zbarimg` y de que el código sea legible en la imagen.
- ComicVine limita las peticiones; cada identificación hace unas pocas consultas.
- Universo Marvel: solo se usan Forum/Planeta, Panini y Vértice (la web tiene unas 25 editoriales más), y el lector
  depende del HTML de esa web, que es antiguo y de varias épocas: si cambia o una ficha es distinta, puede faltar algún
  dato (se avisa, nunca se inventa). Los créditos USA pueden incluir de más cuando la ficha del original no enlaza a tu
  ejemplar (se avisa con «Revisa»). Hay enlaces rotos en la propia web.
- El «Coste» de GCstar es un campo numérico sin decimales en su modelo de cómics: el valor se guarda bien, pero su
  ventana podría mostrarlo redondeado (sin comprobar en GCstar).
- La lista de series supone que una carpeta es una serie: en carpetas sueltas o de eventos, con varias series
  mezcladas y sin metadatos, no se calculan huecos.

## Datos de terceros

Los datos de GCD son © Grand Comics Database (<https://www.comics.org/>) y se distribuyen bajo
licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). El índice local que genera
la aplicación es una obra derivada y debe conservar esa atribución y licencia si se comparte.

Los datos de las fichas de Universo Marvel (fichas.universomarvel.com) pertenecen a sus autores, y los personajes y
publicaciones a sus titulares. La base local (`universomarvel.db`, con las fichas y portadas que consultas) es para tu uso
personal: no la redistribuyas.

Los datos de Tebeosfera (www.tebeosfera.com) son de la Asociación Cultural Tebeosfera y de sus colaboradores (sus textos
se distribuyen con licencia CC BY-SA 4.0 y las imágenes son de sus titulares). La base local (`tebeosfera.db`, con las
fichas y portadas que consultas) es para tu uso personal.

## Licencia

Este proyecto se distribuye bajo la GNU General Public License, versión 3 (ver `LICENSE`).
