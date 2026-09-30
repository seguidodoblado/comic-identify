<p align="right"><a href="README.en.md">🇺🇸 English</a></p>

<p align="center">
  <img src="comic-identify.svg" alt="Logotipo de Comic Identify" width="128">
</p>

<h1 align="center">Comic Identify</h1>

<p align="center">
  Identifica y cataloga tu colección de cómics digitales (CBR, CBZ, CB7) por portada o por título, con
  Grand Comics Database, Universo Marvel, Tebeosfera y ComicVine.
</p>

<p align="center">
  <img src="docs/screenshot.png" alt="Captura de Comic Identify">
</p>

Aplicación de escritorio (GTK 4 + PyGObject, interfaz en español), de uso personal: sin servidor ni cuenta,
todo vive en tu equipo.

- **Identifica** un cómic a partir de su portada o de su título, con Grand Comics Database (GCD), el catálogo de
  ediciones españolas de Marvel de [Universo Marvel](https://fichas.universomarvel.com/), el de toda la historieta
  editada en España de [Tebeosfera](https://www.tebeosfera.com/), ComicVine y tu propia colección.
- **Normaliza** los nombres de archivos y carpetas según un patrón configurable, con deshacer.
- **Escribe metadatos** `ComicInfo.xml` (el formato que entienden Kavita, Komga y ComicTagger), con deshacer y con
  datos de las fichas de Universo Marvel y de Tebeosfera.
- **Transfiere** el cómic catalogado a tu colección de [GCstar](https://www.gcstar.org/), con su portada.
- **Copias de seguridad** verificadas de sus índices y ajustes, con restauración.
- **Busca dónde comprar** el ejemplar y abre otras webs de cómic.

## Documentación

Toda la documentación —instalación, guía de uso, especificaciones técnicas, solución de problemas y más— está en
la **[wiki del proyecto](https://github.com/seguidodoblado/comic-identify/wiki)** (español e inglés).

## Comprobaciones

```bash
pytest
ruff check .
```

## Datos de terceros

Los datos de GCD son © Grand Comics Database (<https://www.comics.org/>) y se distribuyen bajo
licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). El índice local que genera
la aplicación es una obra derivada y debe conservar esa atribución y licencia si se comparte.

Los datos de las fichas de Universo Marvel (fichas.universomarvel.com) pertenecen a sus autores, y los personajes y
publicaciones a sus titulares. La base local es para tu uso personal: no la redistribuyas.

Los datos de Tebeosfera (www.tebeosfera.com) son de la Asociación Cultural Tebeosfera y de sus colaboradores (sus
textos se distribuyen con licencia CC BY-SA 4.0 y las imágenes son de sus titulares). La base local es para tu uso
personal.

## Licencia

Este proyecto se distribuye bajo la GNU General Public License, versión 3 (ver `LICENSE`).
