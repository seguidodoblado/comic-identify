# Changelog

Todos los cambios relevantes de este proyecto se documentarán
en este archivo.

## [Unreleased]

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
