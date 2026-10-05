# Changelog

Todos los cambios relevantes de este proyecto se documentarán
en este archivo.

## [Unreleased]

## [0.44.2] - 2026-10-05

### Cambiado
- El CD ya no construye el `.deb` por segunda vez: la release publica el mismo `.deb` que el CI construyó y pasó por lintian (artefacto `comic-identify-deb`)
- El identificador de la aplicación (`Gtk.Application`) pasa de `com.example.ComicIdentify`, un valor de ejemplo, a `io.github.seguidodoblado.ComicIdentify`, un identificador real con la forma que exige Flathub; no cambia ningún dato guardado

## [0.44.1] - 2026-10-04

### Changed
- Las pestañas «Identificar», «Mi colección» y «Ajustes» llevan un icono del tema del sistema, junto al texto
- La ventana «Acerca de» sigue el estándar de los demás proyectos: licencia GPL-3.0 o posterior (la declara también `debian/copyright`, como GPL-3+) predefinida de GTK (`GPL_3_0`) en lugar de un texto propio, correo del autor como enlace y créditos de traducción (`translator-credits`, en `po/en.po`)

## [0.44.0] - 2026-10-04

### Added
- **Interfaz en español e inglés** (#9): toda la interfaz, los avisos y los mensajes de error pasan por `gettext`. El idioma fuente es el español y el catálogo inglés está en `po/en.po` (590 mensajes); se elige en **Ajustes** (Sistema, Español o English; reinicia la aplicación conservando el cómic abierto) o, con «Sistema», por el idioma del escritorio o `$LANGUAGE`. Los catálogos se compilan al empaquetar y en el CI, y no se versionan; ver `po/README.md`. No se traduce lo que es dato o clave (campos de `ComicInfo.xml`, variables del patrón de nombres, nombres de fuentes y tiendas, valores que se escriben en los archivos)

### Changed
- **El despliegue (CD) solo corre si el CI está en verde**: `cd.yml` llama a `ci.yml` como workflow reutilizable (`workflow_call`) y la release depende de él (`needs: ci`), de modo que una etiqueta con tests, ruff o lintian en rojo no genera borrador
- El estado de cada serie y el filtro de la lista de series ya no dependen del texto traducido: usan claves estables (`SeriesReport.status_key`), y el aviso de metadatos se pinta como advertencia por una marca, no buscando palabras en el texto

## [0.43.1] - 2026-10-04

### Changed
- La interfaz gráfica pasa a vivir en el paquete `comic_identify.ui`: `gui.py`, `theming.py`, `icons.py`, `logos.py` y `webfilter.py` se mueven a `src/comic_identify/ui/`, como en Bloguero. Es una reorganización interna, sin cambios de comportamiento

## [0.43.0] - 2026-10-03

### Added
- **API pública de GCD como último recurso en «Usar esta ficha»** (#12): si el número de la ficha abierta no está en
  el índice local importado, se consulta la API pública de comics.org (ficha, serie y editorial; con pausa entre
  peticiones) para rellenar los mismos metadatos que ya daba el índice local. No sustituye la búsqueda por texto
  (la API no la permite) ni trae la portada (sigue bloqueada por Cloudflare).

## [0.42.0] - 2026-10-02

### Added
- **Tema del sistema**: en Ajustes, junto a Claro y Oscuro, un tercer botón «Sistema» que sigue el tema claro/oscuro
  del escritorio en vez de fijar uno elegido.

### Fixed
- **Aclaración sobre la 0.40.0**: el aviso de consentimiento de cookies de Universo Marvel no quedó resuelto con aquella
  versión (dejar de bloquearle las cookies no bastó). Sigue siendo un problema conocido.

## [0.41.3] - 2026-10-02

### Added
- **Despliegue automático de la release (CD)**: nuevo workflow `cd.yml` de GitHub Actions que, al subir una etiqueta
  `vX.Y.Z`, comprueba que coincide con `debian/changelog`, construye el `.deb`, le pasa lintian y deja la release en
  **borrador** con el `.deb` adjunto, las notas de `debian/changelog`, las notas autogeneradas de GitHub y el SHA-256.
  La release se revisa y se publica a mano desde GitHub.
- Insignias de la métrica de tiempo de programación (CodeTime y WakaTime) en los README.

## [0.41.2] - 2026-10-02

Incluye también los cambios de empaquetado de la revisión 0.41.1-1ubuntu1 (más abajo).

### Fixed
- **La primera petición a Universo Marvel y a Tebeosfera ya no espera de más en un equipo recién arrancado.** El marcador de
  «aún no hubo petición» valía `0.0` y se comparaba con `time.monotonic()`, que cuenta desde el arranque: con menos
  segundos de uptime que el intervalo entre peticiones (1,5 s), la primera esperaba sin necesidad. Ahora vale `-inf`. En uso
  normal apenas se notaba; hacía intermitente un test del CI en máquinas recién arrancadas.

### Added
- Un test por módulo para ese caso (primera petición sin espera con el reloj «joven», segunda con la espera debida).

## [0.41.1-1ubuntu1] - 2026-10-02

Revisión solo de empaquetado: el código de la aplicación no cambia.

### Changed
- **El `.deb` pasa lintian sin errores, avisos ni notas.** Incluye `copyright` y `changelog.Debian.gz`, páginas de manual en
  inglés y en español (`man comic-identify`), `Keywords` en la entrada de escritorio y una única categoría (`Graphics`).
- **La aplicación se instala en `/usr/share/comic-identify`** en lugar de `/opt/comic-identify`.
- **Los permisos del paquete son fijos** (755 en directorios, 644 en ficheros) y ya no dependen de la `umask` de quien lo construye.

### Added
- **Workflow de CI** (`.github/workflows/ci.yml`): `ruff` y `pytest`, y construcción del `.deb` con lintian, que falla ante errores.
- Insignias de estado en los README, en español e inglés.

## [0.41.1] - 2026-10-01

### Changed
- **El README se ha simplificado y ahora tiene versión en inglés** (`README.en.md`), con una captura de pantalla y enlaces
  a Universo Marvel y Tebeosfera en «Datos de terceros»; se añade el crédito a Comic Vine y se quitan las comprobaciones
  que estaban duplicadas.
- **El `.deb` toma su versión de `debian/changelog`** (ahora versionado en el repositorio) en lugar de `pyproject.toml`;
  `build-deb.sh` se niega a construir si la versión del changelog, la de `pyproject.toml` y la de `__init__.py` no coinciden.

## [0.41.0] - 2026-09-29

### Fixed
- **GCD dejaba de pasar la comprobación «no soy un robot» de Cloudflare** desde la 0.39.0: el panel se identificaba como
  un Chrome normal para evitar avisos de consentimiento en Universo Marvel, pero un WebKit de verdad que dice ser Chrome
  resulta más sospechoso para Cloudflare que uno sincero. Se deshace: el panel vuelve al User-Agent de fábrica de WebKit.
- **El logotipo de una editorial sin el suyo propio podía colarse en una con logotipo automático** si compartían una
  palabra: «Planeta Comic» (`planeta-comic.png`) se ponía por error en las filas de «Planeta DeAgostini», que no tiene
  archivo propio, porque «planeta» es una palabra de las dos. La búsqueda por palabras (pensada para Tebeosfera, que
  antes de consultar una ficha solo trae un trozo del nombre) ya no se usa para las 8 editoriales con logotipo
  automático, que tienen su nombre corto exacto y no lo necesitan.

## [0.40.0] - 2026-09-29

### Fixed
- **El aviso de consentimiento de Universo Marvel seguía saliendo en cada ficha pese al arreglo de la 0.39.0**: la causa
  real era que, desde la 0.34.0, se le bloqueaban todas las cookies por error; a quien la Unión Europea le exige ese
  aviso, la web necesita una cookie para recordar que ya lo aceptó, y al bloquearla nunca podía recordarlo. Ahora ya no
  se le bloquean las cookies a Universo Marvel (solo a Tebeosfera, donde además se bloquea su publicidad); siguen sin
  guardarse en disco, solo mientras la aplicación está abierta.

## [0.39.0] - 2026-09-29

### Fixed
- **Avisos de consentimiento de cookies innecesarios en el panel de Universo Marvel**: el panel se identificaba con el
  User-Agent por defecto de WebKit, que dice «Safari Version/60.5» (una versión que no existe: fallo antiguo y conocido
  de esa librería). Algunas webs con publicidad no lo reconocen como un navegador real y muestran su aviso de
  consentimiento completo cada vez, cosa que un Chrome o Firefox normal no ve. El panel ahora se identifica como un
  Chrome de escritorio normal; las peticiones automáticas siguen identificándose como `comic-identify`.

## [0.38.0] - 2026-09-28

### Fixed
- **El botón «Eliminar datos» ensanchaba la ventana**: quedaba pegado al borde derecho de la columna de la portada en vez
  de junto al texto «ComicInfo.xml», y con datos largos podía desplazarlo todo. Ahora va justo al lado del texto y los
  datos largos se ajustan con el propio scroll de esa columna.

## [0.37.0] - 2026-09-28

### Added
- **Botón «Eliminar datos» en ComicInfo.xml**: quita el ComicInfo.xml entero del archivo abierto (no campo a campo, para
  empezar de cero), junto a la etiqueta de esa sección; solo se activa si el archivo ya tiene uno. Es una escritura de
  metadatos más: se anota en el mismo registro y se deshace igual con «Deshacer» en Ajustes.
- **Editorial Ivrea** entre las webs de compra (grupo Editorial, junto a Panini): busca en La Comiquería, su tienda
  oficial (su propia web no tiene precio ni ficha por tomo, así que no sirve como fuente de metadatos: ver más abajo).

### Removed
- **Zona Negativa** de «Buscar en otras webs»: nunca daba buenos resultados.

## [0.36.0] - 2026-09-28

### Added
- **«Usar esta ficha» también en GCD**: al navegar por comics.org dentro del panel hasta la ficha de otro ejemplar, aparece
  el botón y lo convierte en el resultado elegido, con sus datos; al ser un índice local no hace falta ninguna consulta,
  se resuelve al momento (a diferencia de Universo Marvel y Tebeosfera, que sí piden su ficha).

## [0.35.0] - 2026-09-28

### Fixed
- **El logotipo del usuario no salía en las series de Tebeosfera sin resolver** (antes de escribir el número y consultar su
  ficha): Tebeosfera solo trae el trozo de editorial de la dirección de la serie («Surco»), no el nombre completo que dan
  GCD o Universo Marvel («Ediciones Surco»), y no encontraba el archivo guardado con ese nombre. Ahora, si no hay un archivo
  con el nombre exacto, se busca uno cuyas palabras coincidan con las del nombre (en cualquier sentido), así que sirve el
  mismo archivo venga el nombre de donde venga.

## [0.34.0] - 2026-09-28

### Changed
- **Sin cookies en el panel web**: Universo Marvel no deja ninguna, a Tebeosfera se le bloquean todas y GCD deja solo
  `cf_clearance`, la de la comprobación anti-robots de Cloudflare (sin ella la página se queda en «Un momento…», lo he
  comprobado), que ya solo vive en memoria y se pierde al cerrar la aplicación. Se revierte el guardado de cookies en disco de
  la 0.33.0 (`cookies.sqlite`, que además se borra al arrancar) y se quita de GCD la medición de visitas de Cloudflare.

## [0.33.0] - 2026-09-28

### Changed
- **Fichas de Tebeosfera más ligeras y sin avisos de cookies**: el panel bloquea los servicios de medición y publicidad de
  terceros que cargaba cada ficha (Google Tag Manager, Analytics y publicidad de Google, Ahrefs, Tailwind por CDN) y las
  imágenes de anuncios propios de la web. Una ficha pasa de ~6 MB y 109 peticiones a ~1,3 MB, ya no deja cookies de
  seguimiento y no muestra su aviso de cookies. Solo afecta a las páginas de Tebeosfera.

### Fixed
- **Las cookies del panel web no se guardaban en disco** (en contra de lo que decía el código): había que volver a aceptar
  avisos de cookies y a pasar la comprobación de Cloudflare de GCD en cada arranque. Ahora se guardan (`cookies.sqlite`).

## [0.32.0] - 2026-09-28

### Changed
- **Créditos**: Ajustes y «Acerca de…» reconocen ahora a Universo Marvel y a Tebeosfera, con su icono, qué aportan y su enlace, igual
  que a Comic Vine y GCD (la presentación pasa de «dos» a «cuatro comunidades de colaboradores»).

## [0.31.0] - 2026-09-28

### Added
- **Universo Marvel con todas sus editoriales**: además de Forum/Planeta, Panini y Vértice, el índice recoge Bruguera y otras
  27 (Manhattan, Ferma, Laida, Novaro, Montena, Distrinovel, Surco, Rasgos, Zinco, Norma, Vid, Sword Studio, Dolmen, Kraken, ECC,
  Diábolo, Ediciones Recreativas, Dronte, Toutain, Nueva Frontera, Ediprint, Hitpress, Editorial Valenciana, Ediciones B, Yermo,
  Cartem y Producciones Editoriales), cada una con su editorial tal como la nombra la web. **Hay que volver a descargar el
  índice** (Ajustes: 31 peticiones, casi un minuto); las fichas ya consultadas no se pierden.

## [0.30.0] - 2026-09-28

### Changed
- **Orden de los resultados**: tu colección siempre primero y, después, Tebeosfera, Universo Marvel y GCD (antes GCD iba
  delante). Con una portada abierta, tu colección y el código de barras exacto van primero y luego el parecido de portada.

### Added
- **Tebeosfera** como nueva fuente, con todas las editoriales y épocas y el mismo funcionamiento que Universo Marvel:
  índice local (Ajustes → «Descargar el índice de Tebeosfera»: ~13 peticiones a sus sitemaps públicos, unas 44.000 colecciones
  y ~490.000 números), sugerencias al escribir con chip naranja e icono, ficha del ejemplar al elegir una colección con su
  número (o «Usar esta ficha» al navegar por la web en el panel), portada con su **parecido con la tuya**, barra de progreso,
  logotipo de la editorial, copia de seguridad del índice y ficha en el panel derecho.
- Sus metadatos: año, mes y día, total, editorial y sello, idioma, formato, web, **todos los créditos** (guion, lápiz, tinta,
  color, rotulación, portada, traducción, edición), género, sagas como personajes, título, ISBN/EAN, Blanco y negro y, en las
  Notas, los datos de la edición, las ediciones relacionadas y el texto de la ficha. El coste (pesetas convertidas) y el ISBN
  llegan a «Transferir a GCstar…».
- Si el número escrito no existe en una colección, se ofrecen los más cercanos para elegir.

## [0.29.0] - 2026-09-28

### Added
- **Transferir a GCstar**: la traducción y la edición del ComicInfo.xml (GCstar no tiene campos para ellas) van al final del
  comentario, como «Traducción: …» y «Edición: …», solo si hay dato.
- **Transferir a GCstar**: el `BlackAndWhite` del ComicInfo.xml pasa a las **etiquetas** de GCstar: «Color» (No) o «B&N» (Yes),
  escritas con el mismo formato que usa el propio GCstar (`<tags><line><col>…</col></line></tags>`, comprobado con un item
  creado por él). Sin dato, sin etiqueta.

## [0.28.0] - 2026-09-28

### Added
- **Comprar → Todas**: abre la búsqueda del ejemplar en las ocho tiendas a la vez, cada una en su pestaña, como el «Todas»
  de «Buscar en otras webs».
- **Usar esta ficha**: al navegar por Universo Marvel en el panel derecho hasta la ficha de un ejemplar, aparece ese botón
  y la ficha pasa a ser el resultado elegido, con sus créditos, mes, traducción, portada, etc. (antes, si llegabas a una
  ficha haciendo clic en el panel, el resultado elegido seguía siendo la serie y «Metadatos archivo» no traía sus datos).
- Si una serie lista sus fichas por título y no por número (Amalgam…), al no encontrar el número escrito se ofrecen sus
  fichas (hasta 30) en la lista para elegir una.
- **Blanco y negro** (`BlackAndWhite` de ComicInfo.xml) desde la ficha de Universo Marvel: «Yes» si dice blanco y negro,
  «No» si dice color; se escribe al aplicar los metadatos de un solo archivo.

## [0.27.0] - 2026-09-28

### Added
- **Créditos, género, personajes y más de GCD en los metadatos**: el índice de GCD importa ahora las historias de cada número y
  sus créditos (del modelo nuevo de «creadores» del volcado, el que muestra comics.org: el 75 % de las historias tiene
  alguno frente al ~30 % del texto antiguo), y con un resultado de GCD **con número** elegido y un solo archivo,
  «Metadatos archivo…» precarga guion, lápiz, tinta, color, rotulación, edición, traducción y autor de la portada, además del
  género (traducido si se conoce), los personajes, la fecha, la web del número, el código de barras y la sinopsis. Los
  traductores (anotados en GCD como «guion» con la nota «traducción») van a Traducción; una historia sin créditos propios
  hereda los de la original reimpresa; con varias historias, las Notas llevan «Créditos por historia (GCD)». El
  «Coste» de «Transferir a GCstar…» sale de GCD si da el precio en euros o pesetas (convertidas).
- Nuevos campos en el diálogo de Metadatos: **Género**, **Personajes** y **Edición** (`Genre`, `Characters` y `Editor`).
- **Hay que volver a importar el volcado de GCD** (Ajustes; unos 12 segundos) para tener esos datos: el índice pasa de
  ~15 MB a ~40 MB. Un índice de la versión anterior sigue sirviendo para buscar, y Ajustes avisa de que no trae créditos.

## [0.26.3] - 2026-09-28

### Fixed
- **Los logotipos que pones a mano salían enormes y descentrados** (p. ej. uno cuadrado de 900 px salía de unos 80 px de alto
  y desplazado del borde derecho): GTK no reescala bien una imagen grande dentro de un hueco pequeño. Ahora se reducen al
  hueco de las filas (116×24 px, conservando la proporción) y quedan alineados a la derecha como los descargados; vale
  PNG, JPG y SVG de cualquier tamaño, y uno ilegible se ignora (sale la etiqueta con el nombre).

## [0.26.2] - 2026-09-28

### Fixed
- **El panel de WebKit (fichas de GCD y de Universo Marvel) seguía rompiendo el ancho de la pantalla** después de haber usado
  el terminal del asistente: el panel derecho reservaba el ancho de su página más ancha aunque estuviera oculta, y la
  cabecera («Ficha…», «Abrir en el navegador», «Volver al asistente», cerrar) no podía encogerse, así que el mínimo
  de la ventana pasaba de la pantalla (con letra grande, hasta 2081 px en una de 1920) y dejaba de poder maximizarse.
  Ahora solo cuenta la página visible y el título de la cabecera se recorta en vez de ensanchar el panel; probado con un
  gestor de ventanas real, la ventana maximizada y tres tamaños de letra. La corrección de 0.26.1 solo cubría la primera
  apertura del terminal.

### Changed
- **Abrir, arrastrar o pegar un cómic nuevo cierra el panel derecho** si estaba abierto con la ficha (o la sesión de IA) del
  anterior. Solo se cierra cuando el nuevo se ha cargado de verdad: si falla la lectura, el panel se queda como estaba.

## [0.26.1] - 2026-09-28

### Fixed
- **Abrir el asistente de IA (o cualquier panel derecho) sacaba la ventana de la pantalla y le quitaba el maximizar**: el
  panel pedía 760 px fijos y la ventana crecía otros tantos aunque ya estuviera maximizada; con una letra algo mayor,
  la parte izquierda más el panel superaban el ancho de la pantalla y el gestor de ventanas dejaba de permitir
  maximizar. Ahora el panel se adapta al espacio que da la pantalla (con un mínimo de 420 px), la ventana nunca crece más
  que la pantalla y, si está maximizada o a pantalla completa, no se toca su tamaño.

### Changed
- README: descripción del tema claro/oscuro y del ajuste del panel derecho al ancho de la pantalla.

## [0.26.0] - 2026-09-28

### Added
- **Tema claro y oscuro**, con el mismo criterio que Telegraph Writer y Joseflix: en **Ajustes** los botones «Claro» y
  «Oscuro» cambian al tema hermano del que tenga el sistema (conservando el acento: `Mint-Y-Aqua` <-> `Mint-Y-Dark-Aqua`); en
  oscuro se usan los iconos simbólicos y en claro los de color de tu tema de iconos. Se guarda en `config.json`
  (`dark_mode`) y se aplica al arrancar; mientras no elijas, sigue al sistema. Cambiarlo reinicia la aplicación (en
  Cinnamon/Mint no se repinta una ventana ya presentada), conservando el cómic abierto, los campos y la pestaña.
- **Marca de la editorial en todas las filas de GCD**: las que no tienen logotipo propio muestran una etiqueta con su nombre
  (sin «S.A.» ni similares), así que ninguna queda sin marca. Para poner el logotipo de una editorial basta guardar un
  archivo `<editorial>.png` (`.jpg` o `.svg`) en `~/.local/share/comic-identify/logos`; el nombre exacto se ve en la ayuda
  de la etiqueta (p. ej. `ediciones-b.png`). También sirve para cambiar los que se descargan (`forum.png`, `ecc.png`…).

### Changed
- **Etiquetas de fuente en color y con su icono** en cada resultado: GCD en morado, Universo Marvel en rojo y ComicVine
  en verde, con el icono de su web a la izquierda de la etiqueta (las de «Mi colección» siguen como texto discreto).
- **Margen** entre la zona central (campos, botón «Limpiar», lista de resultados y sus logotipos) y el panel de la
  derecha: antes tocaban el borde del panel.

### Added
- **Logotipo de Planeta DeAgostini** en los resultados (GCD y Universo Marvel) cuya editorial es Planeta DeAgostini sin
  sello Forum: sus números de DC, Vértigo o sin sello no llevaban logotipo. Si el sello es Forum sigue saliendo el de Forum.
- **Logotipos de ECC Ediciones, Zinco, Norma Editorial y Bruguera** (las editoriales con más series de España en el índice de
  GCD que aún no tenían logotipo), descargados de la misma web de fichas.

## [0.25.0] - 2026-09-28

### Changed
- El README (y la descripción del paquete `.deb`) se han puesto al día: Universo Marvel, copias de seguridad, Comprar,
  transferencia a GCstar y metadatos ampliados estaban sin documentar o documentados a medias; la sección de Universo Marvel
  se ha reordenado, y se añaden sus limitaciones y el aviso de datos de terceros.

### Added
- **Comprar**: un menú junto a «Buscar en otras webs» que abre en tu navegador la búsqueda del ejemplar (serie, número y
  editorial o sello del resultado elegido o, si no hay, lo escrito en los campos) en Panini, en webs de segunda mano
  (Todocolección, eBay.es, Wallapop, Milanuncios e Iberlibro) y en tiendas (Amazon.es y Casa del Libro). Forum/Planeta y
  Vértice ya no publican, así que sus números solo se encuentran de segunda mano. Sin enlaces de afiliado; usa la misma
  casilla de «Incluir también la editorial y el año».
- **Logotipos de las editoriales** (Forum, Panini y Vértice) en pequeño, a la derecha de cada resultado de Universo
  Marvel y de GCD cuya editorial o sello se reconoce, en un hueco de tamaño fijo. No se incluyen en el paquete (son
  marcas de sus editoriales): se descargan una sola vez de la web de fichas a la caché del usuario
  (`~/.cache/comic-identify/logos`), ya reducidos, y si no se pueden descargar la fila queda sin logotipo y no se
  vuelve a intentar hasta pasada una semana.

## [0.24.0] - 2026-09-28

### Added
- **Sinopsis en el Resumen**: con una ficha de Universo Marvel elegida y un solo archivo, el campo Resumen del archivo
  se precarga con la sinopsis de las historias USA que recoge (la de la ficha del original; muchas no la tienen y
  entonces no se rellena nada). Con varias historias, cada una con su título en un solo párrafo. Si el archivo ya
  tenía un Resumen, no se pisa; de ahí pasa a la sinopsis de GCstar al transferir.
- **Barra de progreso pulsante** en las consultas a Universo Marvel, como la de ComicVine: al elegir una serie con su
  número (ficha y portada), al abrir Metadatos con una ficha elegida (fichas USA) y al descargar el índice en Ajustes.
  Las barras de ComicVine y de Universo Marvel no se pisan si coinciden.

## [0.23.0] - 2026-09-28

### Added
- **Formato**: con una ficha de Universo Marvel elegida, el formato que la ficha indica («Tomo tapa blanda»…, solo lo
  traen algunas) se precarga en un campo nuevo «Formato» del diálogo de Metadatos (`Format` de ComicInfo.xml, con un
  solo archivo) y de ahí en el «Formato» de «Transferir a GCstar…», que sigue ofreciendo los valores que ya usas.
- **Autor de la portada en GCstar**: `CoverArtist` de ComicInfo.xml (que con una ficha de Universo Marvel sale de los
  autores de su portada) se transfiere ahora al campo «Cover Artist» de GCstar (`artist`).
- **Guion, lápiz, tinta y color desde las fichas USA**: con una ficha de Universo Marvel elegida y un solo archivo,
  «Metadatos archivo» consulta la ficha del original USA de cada historia (el enlace «Contenido USA») y precarga esos
  cuatro créditos, sin repetir nombres (el argumento cuenta como guion). De cada ficha USA solo se usan las historias
  que enlazan a la ficha española de tu ejemplar (un número USA trae varias y el español puede recoger solo alguna);
  si no se puede saber cuáles, se usan todas y se avisa. La rotulación y la traducción siguen viniendo de la ficha
  española. Cada ficha USA se descarga una vez (con pausa entre peticiones) y queda en la base local; un enlace roto
  (hay alguno en la web) no impide los demás y se avisa en el diálogo. Si los créditos ya estaban en el archivo, no se
  pisan.
- **Créditos por historia en las Notas**: como un ejemplar puede reunir historias de autores distintos y los campos
  solo admiten una lista por rol, las Notas llevan además, bajo «Contenido USA», un «Créditos por historia (USA)» con
  una línea por historia («Título» (Serie #N): Argumento · Guión · Lápiz · Tinta · Color). Si las Notas ya llevaban un
  bloque de la ficha se refresca en vez de repetirlo; si hay algo escrito a mano debajo, no se toca.
- **Parecido de la portada con la ficha**: al elegir una ficha de Universo Marvel con un cómic abierto, se descarga
  su portada (una petición más, una sola vez), se calcula su huella y se compara con la del archivo, con el mismo
  porcentaje y la misma «Coincidencia probable» que en las sugerencias de ComicVine, más su miniatura en la lista.
  Las portadas se guardan reducidas (500 px) en la base local para no engordarla ni las copias de seguridad.

## [0.22.1] - 2026-09-28

### Fixed
- Con una ficha de Universo Marvel elegida, el campo «Web» de los metadatos (y el «Web» de GCstar al transferir) llevaba
  la página de la **serie**; ahora lleva la de la **ficha del ejemplar**, que es de lo que traen los datos.

## [0.22.0] - 2026-09-28

### Added
- **Universo Marvel** (fichas.universomarvel.com) como fuente local, como GCD: el catálogo de las ediciones españolas
  de Marvel (Forum/Planeta, Panini y Vértice: unas 3.350 series). «Descargar el índice de Universo Marvel», en
  Ajustes, lo baja en tres peticiones espaciadas (unos 4 segundos) y lo guarda en una base local; después las series
  salen en las sugerencias al escribir y al buscar, junto a las de GCD.
- **Fichas de Universo Marvel bajo demanda**: al elegir una serie con el número escrito se consulta solo la ficha de
  ese ejemplar (fecha, precio, páginas, formato, código de barras, rotulación, traducción, autores de la portada,
  historias y enlace al ejemplar USA original) y sale como un candidato con esos datos. Cada página se descarga una
  vez y queda en la base local, con su HTML original para poder releerla sin volver a pedirla si mejora el lector. Las
  series largas que reparten sus números por rangos («1-100», «101-200»…) solo descargan el rango que hace falta.
  Con un candidato de Universo Marvel elegido, **Normalizar nombre** rellena nombre, volumen, bandera 🇪🇸, año,
  sello y editorial, y **Metadatos archivo** añade año, mes, editorial, sello, serie, web y los créditos de la edición
  (rotulación, traducción y portada); con un solo archivo, además, el título del cómic y el código de barras
  (`GTIN`). Esos datos de un solo ejemplar no se ofrecen al etiquetar una carpeta entera.
- **Ejemplares USA y comentarios de la edición en las Notas**: con una ficha de Universo Marvel elegida y un solo
  archivo, las Notas del diálogo de Metadatos llevan, debajo de «Contenido original», el «Contenido USA» (cada
  ejemplar original con el enlace a su ficha) y los «Comentarios de la edición»; de ahí pasan al comentario de GCstar
  al transferir. Si las notas ya tenían algo, se añade debajo sin tocarlo y sin repetirlo. Por eso las Notas pasan a
  ser un campo de varias líneas (con desplazamiento) y la ventana de Metadatos es algo más alta.
- **`PageCount`** en ComicInfo.xml: al escribir metadatos se cuentan las imágenes del propio archivo (no las páginas
  que diga ninguna ficha) y se deja siempre al día; antes no se escribía nunca. Un archivo sin páginas legibles no
  lo recibe.
- **Coste e ISBN en «Transferir a GCstar…»**: dos campos nuevos en el diálogo. Con una ficha de Universo Marvel
  elegida vienen rellenos: el coste en euros (las pesetas se convierten al cambio oficial, 166,386, para no mezclar
  monedas en una misma columna) y el ISBN si la ficha lo trae. El precio no existe en ComicInfo.xml, así que solo se
  conoce por la ficha elegida al transferir (y se puede corregir a mano). El ISBN del `.gcs` ya no se rellena con un
  código de barras que no lo sea (p. ej. el 977… de una revista); en ComicInfo.xml, `GTIN` es el ISBN si la ficha lo
  tiene y, si no, el código de barras.
- **Traducción** en los créditos del diálogo de Metadatos (campo `Translator` de ComicInfo.xml); los créditos pasan a
  tres columnas para ocupar el mismo alto.
- Volver a descargar el índice de Universo Marvel no borra las fichas ya consultadas. Entra en las copias de seguridad.

## [0.21.0] - 2026-09-28

### Added
- **Copias de seguridad y restauración** de los datos de la aplicación (índice de la colección, índice de GCD,
  ajustes y registros de deshacer), en Ajustes: un `.zip` verificado (SHA-256 y comprobación de las bases) por copia.
  Automática al cerrar la aplicación si algo ha cambiado (se conservan las N últimas), manual con «Copiar ahora»
  (nunca se borra sola) y «Restaurar una copia…», que comprueba todo antes de tocar nada y guarda el estado actual
  como copia «antes de restaurar».

### Changed
- El menú «Buscar en otras webs» agrupa las webs en Generalistas, Marvel y DC; «Todas» sigue arriba y abre las nueve.

## [0.20.4] - 2026-09-28

### Changed
- **Transferir a GCStar**: el campo «Publicado por» lleva ahora «Editorial - Sello» en vez de solo la editorial, ya
  que GCstar no tiene campo para el sello y así no se pierde. Si falta uno de los dos, se queda solo el otro.

## [0.20.3] - 2026-09-27

### Added
- **«Todas»** en el menú «Buscar en otras webs»: abre la búsqueda en las 9 webs configuradas de una vez, cada una
  en su propia pestaña del navegador.

## [0.20.2] - 2026-09-27

### Fixed
- **Transferir a GCStar** no llevaba el campo **Web** de ComicInfo.xml (la ficha de GCD, cuando se elige una serie):
  faltaba en el mapeo de campos, ahora se traslada al campo `webPage` de GCstar.

## [0.20.1] - 2026-09-27

### Added
- **Mes y Día** (opcionales) junto a Año en el diálogo de Metadatos: para el caso poco frecuente en que se conozca
  la fecha exacta de la edición y no solo el año. Al transferir a GCStar, la fecha de publicación llevará el día y
  mes si se han rellenado.

## [0.20.0] - 2026-09-27

### Added
- **Barra de progreso al consultar ComicVine**: buscar con número de ejemplar hace varias peticiones seguidas
  (la serie, sus números, la portada de cada candidato) y puede tardar varios segundos; antes había un único
  mensaje fijo todo ese rato. Ahora una barra (bajo los botones de arriba) pulsa mientras dura, y el mensaje de
  estado dice qué serie se está comparando y cuántas quedan («Comparando con ComicVine (2/3): «Batman»…»). Buscar
  solo en tu colección o en GCD (locales, casi instantáneos) no la muestra.
- **`{editorial}`**, nueva variable para el patrón de nombres (Normalizar nombre y Normalizar carpeta), junto a
  `{sello}`: quién publica el ejemplar (Planeta DeAgostini, Panini…), no el sello impreso en él. Se sugiere desde
  GCD igual que el sello. **Ahora en el patrón por defecto**, como `- {sello} - {editorial}` al final del nombre.
- **Resumen** por archivo en el diálogo de Metadatos (junto a Título): escribe el campo `Summary` de ComicInfo.xml,
  sin límite de longitud propio (el único límite es el de 2 MiB del `ComicInfo.xml` entero).
- **Transferir a GCstar** rellena solo «Categoría» con la que ya tenga el archivo (si la tiene), en vez de dejarla
  en blanco, y **«Tipo»** con «Europeo», «Americano» o «Manga» según bajo cuál de tus carpetas de «Mi colección»
  (`EUROPA`, `USA`, `JAPÓN`) esté el cómic; «Formato» y «Colección» siguen sin sugerencia propia, solo con el
  autocompletado de lo que ya uses en tu `.gcs`. Ninguna de las dos sugerencias depende de en qué disco estén
  montadas esas carpetas, solo de sus nombres, así que sobreviven a mover la colección a otro disco.
- La portada y la contraportada se guardan bajo una carpeta **`comics`** propia, dentro de la carpeta de tu `.gcs`
  (antes, directamente en ella), para poder compartir esa carpeta con otras colecciones de GCstar sin mezclar
  las imágenes de cada una.

### Fixed
- `render()` solo quitaba el separador « - » sobrante al **final** del nombre si el último dato faltaba; con dos
  datos opcionales encadenados (sello y editorial), si faltaba solo uno de los dos —el que no fuera el último—
  quedaba un guion suelto («… - - Forum»). Ahora cada tramo del patrón separado por « - » se evalúa por separado y
  se omite entero si queda vacío, sin más rastro, esté donde esté.

## [0.19.0] - 2026-09-27

### Fixed
- La portada ya no empujaba la ventana más allá de su alto normal cuando un cómic tiene muchos campos de
  metadatos, con los dos botones nuevos (Extraer portada, Transferir a GCstar) debajo: se ha reducido el alto
  mínimo de la portada para que todo quepa sin recortarse. Con pocos metadatos, la portada sigue creciendo con
  normalidad.
- El diálogo de **Metadatos** (con los créditos nuevos, y con lotes de muchos archivos) podía crecer más que la
  pantalla y dejar los botones «Cancelar»/«Escribir metadatos» fuera de la vista, tapados por la barra de tareas.
  Ahora la ventana tiene un tamaño fijo y solo se desplaza el contenido (campos, créditos, categoría, la lista de
  archivos); los botones y el resumen quedan siempre a la vista, fuera de esa zona.

### Added
- **Transferir a GCstar…**: añade el cómic abierto a una colección de GCstar (gcstar.gitlab.io) sin tocar el resto
  de su archivo `.gcs`: solo inserta el `<item>` nuevo justo antes de `</collection>`, con los créditos, la
  editorial, el año, el número de páginas y la ruta del archivo que ya tenemos, más los campos propios de GCstar
  (tipo, categoría, formato, colección) con un desplegable que sugiere lo que ya usas en tu colección. Copia también
  la portada y la contraportada junto al `.gcs`, con la misma estructura de carpetas y el mismo nombre que ya usas
  (`<nombre> - Portada.jpg` / `- Trasera.jpg`); solo si el cómic está bajo una carpeta configurada en «Mi
  colección» (si no, se transfiere sin portada, sin adivinar dónde ponerla). Se niega a escribir si detecta GCstar
  abierto (por su `autosave`, podría sobrescribir esto al cerrarlo) y se puede deshacer por lotes desde Ajustes
  (`~/.local/share/comic-identify/gcstar.log`); el deshacer no toca una portada que haya cambiado desde entonces.
  La ruta al `.gcs` se configura una vez en Ajustes; todo lo demás (dónde van las imágenes, qué valores sugerir,
  el siguiente número de elemento) se lee del propio archivo.
- **Créditos** en el formulario de metadatos (archivo y carpeta): guion, lápiz, tinta, color, rotulación y portada,
  como los demás campos de serie (se aplican a todos los archivos del lote; un campo vacío no se toca).
- **Extraer portada…**: bajo la portada, guarda la primera página como imagen junto al archivo, con su mismo nombre
  y la extensión que ya traía (sin recodificarla, para no perder calidad). Útil para catalogadores externos como
  GCstar, que piden la portada como un archivo aparte. No sobrescribe una imagen que ya exista con ese nombre.
- Un icono ocupa el hueco de la portada mientras no hay ningún cómic abierto.

## [0.18.4] - 2026-09-27

### Changed
- El botón «Abrir cómic…» se llama ahora **«Abrir…»** (el tooltip y el diálogo explican qué abre).
- Se deja claro que **Normalizar nombre** y **Metadatos** actúan sobre el archivo original, no sobre una copia (también
  al abrirlo por pegado o arrastre): una línea discreta en cada diálogo y en los tooltips de los botones, sin avisos
  emergentes; todo sigue siendo reversible desde Ajustes.

### Fixed
- **Pegar un cómic copiado no funcionaba**: el botón «Pegar» (Ctrl+V) decía que admitía un cómic, pero solo leía
  imágenes del portapapeles. Ahora también abre un archivo CBR, CBZ, CB7 o imagen copiado en el gestor de archivos.
  Un archivo de otro tipo, ya sea pegado o arrastrado, se rechaza con un aviso en vez de intentar abrirlo.

## [0.18.3] - 2026-09-27

### Changed
- Las webs de búsqueda: se **quita «ECC (DC)»** (no era la web que se buscaba) y se añaden **«DC Comics»** (`dc.com`,
  la web oficial de DC) y **«Norma Comics»** (`normacomics.com`, la tienda de cómics de Norma, distinta de «Norma»,
  que es `normaeditorial.com`). Como las demás, abren la búsqueda en tu navegador con `site:` en Google. El mensaje
  del asistente las menciona.

## [0.18.2] - 2026-09-27

### Changed
- El terminal del asistente de IA usa la tipografía **Ubuntu Sans Mono** (Regular, 11 pt), con «Monospace» de
  respaldo si no está instalada; sigue cabiendo en 80 columnas.

## [0.18.1] - 2026-09-27

### Changed
- **Botones superiores en una sola línea**: el contenedor limitaba a 6 por línea y son 7, así que el último saltaba
  siempre a la segunda. Ahora admite 7, los textos son más cortos («Pegar», «Metadatos archivo…», «Metadatos
  carpeta…») y la ventana arranca con 1500 px de ancho, que es lo que necesitan; en una ventana más estrecha, siguen
  pasando a otra línea. El orden agrupa por función: normalizar nombre y carpeta, metadatos de archivo y carpeta.
- El botón «Abrir portada…» se llama ahora **«Abrir cómic…»**, porque abre CBR, CBZ y CB7 además de imágenes; el
  diálogo de archivos y el mensaje inicial lo reflejan.

## [0.18.0] - 2026-09-27

### Added
- **Mensaje del asistente configurable**: en Ajustes hay una caja con el texto que sustituye a `{prompt}` en el comando
  (`{image}` es la portada), con botón para restablecer el de la aplicación. El mensaje de serie ahora también
  menciona ECC y DC Database.
- **Webs para DC**: «ECC (DC)» (la editorial de DC en España) y «DC Database» (wiki de DC en inglés, con número original y
  fechas). Como las demás, abren la búsqueda en tu navegador con `site:` en Google; la app no lee esas webs.
- **Iconos de respaldo**: si una web no entrega su icono (DC Database solo sirve a navegadores), se pide al servicio
  público de favicons de Google, al que solo se le envía el nombre del dominio; no se finge ser un navegador. Los
  fallos de iconos anteriores a este cambio se reintentan solos.

### Changed
- Las webs de búsqueda van en un desplegable «Buscar en otras webs» con sus iconos, que se repliega al elegir una,
  en vez de una fila de botones.

### Fixed
- El asistente de IA no encontraba CLIs que solo están en el `PATH` de tu shell (`opencode` en `~/.opencode/bin`,
  `codex` bajo nvm), porque una aplicación lanzada desde el menú no lo ve. Ahora se lanza a través de tu shell
  interactiva, con el mensaje intacto (comillas, `$` y saltos de línea).

## [0.17.0] - 2026-09-27

### Added
- **Doble clic en la página** a la vista: se abre en una ventana grande (casi toda la altura de la pantalla) con las
  mismas flechas, el teclado (←, →, Re Pág, Av Pág, Inicio, Fin, Esc) y un botón «Tamaño real» que la muestra sin
  reducir. Las páginas se leen hasta 3200 px de lado, para poder leer la letra pequeña de una contraportada. Funciona
  también con imágenes sueltas.
- **Panel del ComicInfo.xml** bajo la portada y sus flechas: muestra el `ComicInfo.xml` del archivo abierto (serie,
  número, total, fecha, autores, editorial, sello, categoría, etiquetas, web, notas…) o avisa de que no lo tiene. Se
  actualiza solo al escribir o deshacer metadatos. Ocupa lo que necesita (hasta 260 px, y se desplaza si hay más
  campos) y la portada se queda con el resto del alto; la columna de la portada mide 440 px.
- **Acerca de…**: botón arriba en Ajustes que abre un diálogo con el logo, la versión, el autor, la licencia (GPL v3),
  el enlace al repositorio y la atribución de los datos de terceros (GCD, bajo CC BY-SA 4.0, y Comic Vine).
- `comic-identify --version` muestra la versión sin abrir la aplicación.

### Changed
- La ventana principal arranca con 1100×820 px; la portada se ajusta al alto disponible (antes tenía un tamaño casi fijo).
- El paquete DEB indica el mantenedor y la página del proyecto (antes `Comic Identify <localhost>`).

## [0.16.0] - 2026-09-27

### Added
- **Navegar por las páginas** del CBR/CBZ/CB7 abierto: bajo la portada, botones de primera, anterior, siguiente y
  última página con «Página 3 de 24». Sirve para mirar la contraportada o la primera página, donde a veces salen los
  datos que la portada no tiene. Solo cambia lo que ves: la búsqueda sigue usando la portada. Las páginas se leen en
  segundo plano y se reducen a 1600 px para mostrarlas; al cambiar de cómic no se mezclan.
- **Series de la colección** (pestaña «Mi colección»): lista de las series con lo que tienes y lo que falta
  («12 de 36 · faltan 3, 7, 13-36 · metadatos 10/12 · Series»), con filtro (incompletas, todas, sin todos sus metadatos,
  sin total indicado), búsqueda y botón para abrir la carpeta. Una serie es el conjunto de archivos de una carpeta con la
  misma serie de ComicInfo; los archivos sin metadatos solo forman serie si su carpeta tiene el nombre normalizado
  (bandera o años), no en carpetas sueltas como «Por colocar». El total esperado es el «Total de números» de los
  metadatos; sin él solo se señalan los huecos entre los números que hay y desde cuál empieza. Un número muy alejado del
  resto o mayor que el total se marca como «fuera de la serie» en vez de inventar decenas de huecos, los números
  sueltos no cuentan como serie incompleta, y una carpeta sin metadatos con números repetidos se marca como mezcla de
  varias series.
- El índice de la colección guarda ahora el resumen del `ComicInfo.xml` de cada archivo (serie, volumen, número,
  total, categoría). Un índice anterior se amplía solo y en la primera indexación se leen los metadatos de los archivos
  ya indexados sin volver a calcular sus portadas; escribir o deshacer metadatos también lo mantiene al día.
- **Metadatos…** (botones «Metadatos de la carpeta…» y «Metadatos del archivo…»): escribe el `ComicInfo.xml` (el
  formato que entienden Kavita, Komga y ComicTagger) en CBZ, CBR y CB7, decidiendo el formato por el contenido y no
  por la extensión (ZIP, RAR4, RAR5, 7-Zip). El diálogo tiene los campos de serie (serie, volumen, editorial, sello,
  año, total de números, idioma, web, notas), la **categoría** que eliges tú (se guarda en las etiquetas como
  `Categoría: …`) y una tabla por archivo con su número (el del nombre; los nombres normalizados ` #05` se leen sin
  dudas) y su título. Se rellena, por orden, con lo que ya tienen los archivos, la serie de GCD elegida, el nombre
  de la carpeta o archivo (leído al revés) y lo tecleado en la pantalla principal; un campo vacío no se toca y solo
  se borra un valor si tú lo quitas y todos lo tenían. Se conservan los campos que no se tocan (autores, `Pages`…);
  los números y fechas se validan antes de escribir.
- Escritura segura: se trabaja en una copia junto al original, se verifica (integridad, mismas páginas, XML esperado)
  y solo entonces se sustituye de forma atómica; se comprueba antes el espacio libre y un archivo que falla no
  impide los demás. Los archivos que ya tienen esos valores no se reescriben, y el índice de la colección anota el
  nuevo tamaño para no volver a leer las portadas. Para escribir en RAR hace falta el programa `rar` (sugerido en el
  paquete); para leer, `unrar` o `7z`.
- **Deshacer metadatos** (Ajustes): cada escritura queda registrada (`metadata.log`) con el ComicInfo.xml anterior
  byte a byte; deshacer revierte el último lote entero (restaura el XML anterior o quita el `ComicInfo.xml` si no
  tenía) sin pisar archivos que se hayan modificado o movido después.
- Las carpetas se recorren también en busca de `.cb7` y `.7z`.

- **Normalizar carpeta…**: la carpeta es la serie. Se elige una serie de GCD en los resultados (sin número) y,
  al pulsar el botón y elegir la carpeta, el formulario propone del nivel de serie de GCD: nombre, bandera (por
  país), años de la edición (`2000-2002`, `2006` o `2011-` si sigue publicándose) y el sello más frecuente de
  sus números. Los años del contenido original se ponen a mano o con el botón de ComicVine (que ya recibe el
  primer y el último número de la carpeta). Los archivos de dentro se llaman **como la carpeta
  resultante más ` #01`, ` #02`…** (`Serie 🇪🇸 [1999-2001] (2000-2002) - Forum #01.cbz`), usando **el número que ya
  trae cada nombre**, así que los huecos se respetan; los números llevan **como mínimo dos cifras** (`01`, `02`…)
  y las del número más alto si tiene más (`001` a partir del 100). Avisa si el nombre supera el límite del sistema. Tabla de vista previa
  «antiguo → nuevo» con el número editable y casilla para excluir cada archivo; avisa de archivos sin número,
  números dudosos, repetidos o nombres que ya existen, y no deja aplicar mientras haya un problema.
- El renombrado en lote se hace en **dos fases** (un nombre puede ser el destino de otro archivo del lote) y
  todo o nada: se valida antes de tocar nada y, si la carpeta no se puede renombrar, los archivos vuelven a
  su nombre. Actualiza el índice de la colección (rutas de archivos y de la carpeta) y se deshace **de una
  vez como un lote** desde Ajustes.
- Todos los botones llevan un icono simbólico del tema GTK del usuario junto a su texto (Abrir portada,
  Pegar, Preguntar a la IA, Normalizar, Limpiar, Añadir carpeta, Indexar/Cancelar, Guardar, Deshacer…). Si
  el tema no tiene un icono, el botón queda solo con el texto.
- Botón verde **Limpiar**, junto a los campos: vuelve al estado inicial (quita título, número, editorial y
  año, los resultados, la portada, el panel de la ficha y la sesión de IA). Una búsqueda que aún estaba en
  marcha no vuelve a rellenar los resultados después.
- Casilla «Incluir también la editorial y el año» (marcada por defecto) sobre los botones de búsqueda en
  otras webs: si se marca, esas búsquedas usan también la editorial y el año; si una web se queda sin
  resultados, se desmarca.
- Botón **«Buscar en ComicVine…»** junto a «Contenido [años]» en el formulario de normalizar: con el título
  original (en inglés) y el número inicial (y final, si la edición recoge varios), busca la serie en
  ComicVine, dejas elegir la que corresponde y rellena los años con las fechas de portada de esos números
  (`1999` o `1999-2001`). Necesita la clave de ComicVine y hace tres peticiones por consulta.
- **Normalizar nombre…**: renombra el CBR/CBZ abierto (o el de una coincidencia de «Mi colección») según
  `Estructura.md`: `Título Volumen X 🇺🇸/🇪🇸 [años del contenido] (años de la edición) - Sello`. Un formulario
  modal con los valores propuestos desde la sugerencia elegida, todos editables, y la vista previa del nombre.
  Variables del patrón, configurable en el propio formulario: `{nombre}`, `{volumen}`, `{bandera}`,
  `{contenido}`, `{edicion}`, `{sello}` y `{numero}`. Un número suelto en volumen se escribe «Volumen N»;
  si contenido y edición coinciden se omite el paréntesis; los grupos vacíos y el « - » sin sello se omiten.
  Los años del contenido son opcionales (a veces coinciden o no se conocen): si faltan, el nombre lleva solo
  (años de la edición) y un aviso lo indica. No renombra si el nombre ya existe (nunca sobrescribe) o si el
  patrón no es válido. Actualiza el índice de la colección y registra cada cambio; Ajustes tiene «Deshacer
  el último renombrado». Solo archivos, no directorios.
- Campos **Editorial / distribuidor** y **Año** junto al título y el número, para acotar las búsquedas. En
  GCD la editorial casa también con el sello (por ejemplo, «Forum» encuentra las ediciones de Forum
  aunque figuren bajo Planeta DeAgostini), sin distinguir tildes; con número, el año es el del ejemplar y,
  sin número, basta con que la serie se publicara ese año. En ComicVine se aplican a las series y, con
  número, a la fecha de portada. Con filtros activos, si nada cumple no se muestra ruido.
- Botón **«Buscar en ComicVine»**, con su icono, en lugar de tener que pulsar Enter (Enter sigue
  funcionando en el título y la editorial).
- La ficha de ComicVine del panel muestra **Nombre:**, **Año:** e **Issue:** en negrita y en grande, con
  la portada debajo.
- Ajustes muestra los créditos de Comic Vine y Grand Comics Database, con su icono, una breve explicación
  de qué aportan y un enlace. La página de Ajustes ahora se puede desplazar.
- Los botones de búsqueda en otras webs llevan el icono de cada web. Se descargan la primera vez (el
  favicon de cada sitio, como haría un navegador) y se guardan en `~/.cache/comic-identify/icons`; no se
  distribuyen con la aplicación. Si una web no lo da, se usa un icono genérico. Whakoom y comics.org
  bloquean la descarga directa; el icono de GCD se recoge cuando el panel muestra una de sus fichas.
- Fila «Buscar el título en otras webs» con accesos directos a Tebeosfera, Whakoom, Norma, Panini, Universo
  Marvel (fichas de ediciones españolas de Marvel) y Zona Negativa: abren en tu navegador la búsqueda del
  título y el número tecleados. No se rastrean esas webs desde la aplicación (varias lo prohíben en su
  robots.txt o no tienen API). Panini y Zona Negativa usan su propio buscador; el resto, una búsqueda
  `site:` en Google.
- El mensaje del asistente de IA menciona esas fuentes, para que las consulte sin tener que descubrirlas.
- Botón «Preguntar a la IA»: abre en el panel derecho un terminal embebido (VTE) donde se ejecuta la CLI
  oficial del usuario (por defecto Claude Code) con su propia sesión y un mensaje que pide identificar la
  portada. La aplicación no toca credenciales ni llama a ninguna API. El comando es configurable en
  Ajustes (`claude {prompt}`, `codex {prompt}`, `opencode --prompt {prompt}`…).
- Orden `comic-identify buscar "título" [número]`, que el asistente usa para consultar el índice local
  de GCD.
- Las sugerencias de ComicVine también abren su ficha en el panel derecho, en una vista nativa (portada
  grande, título, editorial y fecha) en lugar de incrustar su web, que carga mucha publicidad. No
  requiere WebKit.
- Búsqueda mientras escribes el título en el índice local de GCD (con una pausa de 300 ms), sin
  necesidad de subir antes una portada.
- Panel de ficha a la derecha: al hacer clic en una sugerencia de GCD se carga su ficha de comics.org
  (con su portada) en un WebView de WebKitGTK, una página por clic y solo si está instalado
  `gir1.2-webkit-6.0`. Usa una sesión propia y persistente; sin WebKit, «Ver ficha» sigue abriendo
  el navegador.
- Las coincidencias de «Mi colección» muestran ahora la miniatura de su portada.
- Fuente Grand Comics Database (GCD) para ediciones en español (España y Latinoamérica): se importa
  una vez el volcado SQLite oficial desde Ajustes y se busca sin red ni límites. Funciona sin clave
  de ComicVine.
- Identificación de portadas: código de barras, GCD, ComicVine y comparación visual.
- Índice local de la colección (CBZ/CBR) para reconocer portadas de cómics que ya tienes.
- Interfaz GTK 4 con abrir, pegar y arrastrar imagen.
- Paquete `.deb` mediante `build-deb.sh`.

### Changed

- La ventana se abre a 1100 px de ancho (antes 1000) y la fila superior de botones pasa a otra línea si no
  cabe: el ancho mínimo baja de 1062 a 845 px.
- «Deshacer el último renombrado» deshace un lote entero cuando el último cambio fue una carpeta.
- Abrir o arrastrar un CBR/CBZ lee su portada en un hilo, con el aviso «Leyendo la portada de…»: la
  ventana ya no se congela (la lectura tarda una mediana de 119 ms y hasta ~1 s, más con escaneos enormes).
  Si llega otra carga o se pulsa Limpiar mientras tanto, la lectura anterior se descarta.
- Los botones de búsqueda en otras webs tenían en cuenta solo el título y el número; ahora también la
  editorial y el año (ver la casilla anterior).
- La descripción del paquete `.deb` y de `pyproject.toml` ya no dice «sin IA» (existe el asistente de IA
  opcional), y el README lo explica.
- El botón «Buscar de nuevo» pasa a ser «Buscar en ComicVine» (hace la misma búsqueda completa).
- En la cabecera del panel, «Abrir en el navegador» queda a la izquierda de «Volver al asistente».
- Abrir un archivo con la aplicación ya abierta (por ejemplo, «Abrir con» desde el gestor de archivos)
  lo carga en la ventana existente; antes se ignoraba.
- El asistente de IA vive en el panel derecho, no en una ventana aparte: el panel se ensancha para el
  terminal y, si abres una ficha mientras la sesión sigue activa, aparece «Volver al asistente». La ×
  cierra el panel y la sesión.
- Se elimina el enlace «Ver ficha» de cada sugerencia: duplicaba «Abrir en el navegador» del panel.
  Sin WebKit instalado, un clic en una sugerencia de GCD abre su ficha en el navegador.
- Sin número, las sugerencias de GCD abren en el panel la galería de portadas de la serie (paginada
  por GCD) en lugar de su ficha.
- El título deja de detectarse automáticamente: el OCR no leía los logotipos de los cómics y rellenaba
  el campo con texto sin sentido. Se elimina Tesseract de las dependencias.
- Las fechas parciales de GCD se muestran sin ceros sobrantes (`1969` en lugar de `1969-00-00`).
- Las sugerencias de GCD muestran el sello editorial («Forum; Marvel Comics», «Panini Comics»…),
  que ayuda a distinguir ediciones. El índice de GCD cambia de esquema: hay que volver a importar el
  volcado desde Ajustes (la app lo avisa y tarda unos segundos).
- La ventana admite también archivos CBR/CBZ (arrastrar o abrir): se usa su primera imagen como portada.

### Fixed

- Un «.cbr» que en realidad es un 7-Zip no se podía leer (solo se probaba con `unrar`) y quedaba como
  ilegible en la indexación. Ahora, si `unrar` no lo lee, se prueba con `7z`.
- Cualquier orden distinta de `buscar` (`--help`, una errata, `search`…) abría la interfaz, y con la
  aplicación ya abierta creaba una ventana nueva. Ahora `--help` muestra el uso y las órdenes
  desconocidas terminan con un error, sin abrir nada; la interfaz solo se abre sin argumentos o con un
  archivo que exista. El asistente de IA prueba esas órdenes, y por eso se duplicaba la ventana.
- Con la aplicación abierta, lanzarla de nuevo reutiliza la ventana en lugar de crear otra.
- La línea de estado no se ajustaba a varias líneas y, con textos largos, obligaba a ensanchar la ventana
  (hasta 1287 px de ancho mínimo); ahora el mínimo es de unos 650 px.
- Un único archivo problemático (por ejemplo, un escaneo enorme que Pillow rechaza como «bomba de
  descompresión») abortaba toda la indexación. Ahora se cuenta como ilegible y el lote continúa;
  Ajustes muestra los nombres de los primeros ilegibles con su motivo («imagen enorme», «sin imágenes
  o archivo dañado», «imagen no válida»).
- Colecciones grandes: la limpieza de portadas de archivos que ya no existen era cuadrática (5 s con
  8.000 cómics; horas con cientos de miles). Ahora es lineal.
- Indexar con un disco desmontado (o una carpeta vacía o inexistente) borraba todo su índice. Ahora se
  conserva y se avisa en Ajustes de qué carpetas no se ha podido acceder.
- Quitar una carpeta de la lista olvida sus portadas al momento, en lugar de esperar a la siguiente
  indexación. Las portadas de carpetas ya quitadas se limpian en la siguiente indexación.
- Las sugerencias de GCD sin número (búsqueda solo por título) no tenían enlace y el panel de la ficha
  no se abría al hacer clic; ahora enlazan a la ficha de la serie.
- El número de ejemplar del código de barras se interpretaba igual para EAN-13 (europeo) y UPC-A
  (americano); ahora se distingue según los datos reales de GCD.
- El icono no aparecía en el panel: el `WM_CLASS` era `__main__.py` en lugar de `comic-identify`.
