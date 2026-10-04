# Traducciones (i18n)

El idioma fuente del código es **español**: los textos de la interfaz se escriben directamente en
español dentro del código (`_("Cancelar")`), y no hace falta ningún catálogo `es.po` — si no hay
traducción cargada, `gettext` devuelve el texto tal cual. El inglés está en `po/en.po`.

El idioma se elige en **Ajustes** (Sistema, Español o English; reinicia la aplicación). Con «Sistema» sale del escritorio o de la variable `$LANGUAGE` (por ejemplo, `LANGUAGE=en comic-identify`). Un idioma nuevo se añade también a `LANGUAGES` en `settings.py` y a los botones de Ajustes.

## Qué se traduce y qué no

Se traduce **lo que ve el usuario**: etiquetas, botones, ayudas, avisos de estado y mensajes de error.
**No** se traduce lo que es dato o clave del programa:

- Nombres de campos de `ComicInfo.xml` (`Series`, `Writer`…), variables del patrón de nombres
  (`{nombre}`, `{volumen}`…), nombres de fuentes y tiendas (Tebeosfera, Panini…), y los valores que se
  escriben en los archivos del usuario.
- Textos que se buscan en páginas web, expresiones regulares, parámetros de las APIs, rutas y claves.
- El mensaje por defecto del asistente de IA (`assistant.PROMPT`): la IA contesta en el idioma del mensaje.

## Añadir o cambiar un texto de la interfaz

1. Envuelve el texto en `_(...)` (importado de `comic_identify.i18n`, o de `..i18n` en `ui/`). Para
   cantidades, `ngettext(singular, plural, n)`.
2. **No** metas `_()` dentro de una f-string ni le pases una variable: `xgettext` solo detecta un literal.
   Saca el texto a una plantilla y usa `.format()` con nombres que se entiendan:
   ```python
   # mal — xgettext no ve "Renombrado":
   mensaje = f"Renombrado: {antes} → {despues}"
   # bien:
   mensaje = _("Renombrado: {antes} → {despues}").format(antes=antes, despues=despues)
   ```
3. Si el texto lleva llaves literales, duplícalas (`{{` y `}}`) y llama a `.format()`.
4. **No uses `_` como variable** en los módulos que importan el traductor (`for _ in …`,
   `lambda _: …`, `a, _ = …`): lo sombrearías. Usa `_unused`, `_button`, etc.
5. Los módulos de `ui/` no necesitan nada más: los textos de nivel de módulo (listas, tablas) también se
   traducen, porque el dominio se liga a la carpeta `i18n/` al importarla.
6. Ejecuta `./i18n-extract.sh` desde la raíz. Regenera `po/comic-identify.pot` y actualiza `po/*.po` con
   las cadenas nuevas (quedan con `msgstr ""` o marcadas `#, fuzzy` si el texto original cambió).
7. Traduce las cadenas nuevas o `fuzzy` a mano en `po/en.po` y quita la marca `#, fuzzy` una vez revisadas.
   Conserva los `{nombre}` tal cual, los espacios del principio y del final, las etiquetas `<b>` y los
   saltos de línea.
8. Ejecuta `./i18n-compile.sh` para generar los `.mo` y prueba la aplicación:
   ```sh
   LANGUAGE=en python3 -m comic_identify
   ```

`build-deb.sh` ya llama a `i18n-compile.sh`, así que el paquete siempre lleva los catálogos compilados.
El CI también los compila antes de ejecutar las pruebas.

## Añadir un idioma nuevo

```sh
msginit --input=po/comic-identify.pot --locale=<código> --output=po/<código>.po
```

Traduce `po/<código>.po` y compílalo con `./i18n-compile.sh`: detecta cualquier `po/*.po` solo, no hace
falta tocar el script.

## Créditos de traducción

Cuando el «Acerca de» use `translator_credits=_("translator-credits")`, cada `po/<código>.po` pondrá en el
`msgstr` de esa entrada a sus traductores, uno por línea (`\n`) y con `<correo>` opcional. No cambies el
`msgid ""` de la cabecera del fichero: es el de la cabecera, no el de los créditos.

## Pruebas

Las pruebas fijan `LANGUAGE=es` en `tests/conftest.py`, así que no dependen del idioma de tu equipo.
`tests/test_i18n.py` comprueba el catálogo inglés (necesita los `.mo` compilados) y que las traducciones
conservan los `{nombre}` del original.

## Dónde vive cada cosa

- `po/*.po`, `po/comic-identify.pot`: fuente de las traducciones, versionado en git.
- `src/comic_identify/i18n/<idioma>/LC_MESSAGES/comic-identify.mo`: catálogo compilado, **no** se
  versiona (está en `.gitignore`), se genera con `i18n-compile.sh`.
- `src/comic_identify/i18n/__init__.py`: `install()` (se llama una vez al arrancar), `_()` y `ngettext()`.
