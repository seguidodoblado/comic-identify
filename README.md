<p align="right"><a href="README.en.md">🇺🇸 English</a></p>

<p align="center">
  <img src="comic-identify.svg" alt="Logotipo de Comic Identify" width="128">
</p>

<h1 align="center">Comic Identify</h1>

<p align="center">
  <a href="https://github.com/seguidodoblado/comic-identify/releases"><img src="https://img.shields.io/github/v/release/seguidodoblado/comic-identify" alt="release"></a>
  <a href="https://github.com/seguidodoblado/comic-identify/actions/workflows/ci.yml"><img src="https://github.com/seguidodoblado/comic-identify/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/seguidodoblado/comic-identify/actions/workflows/cd.yml"><img src="https://github.com/seguidodoblado/comic-identify/actions/workflows/cd.yml/badge.svg" alt="CD"></a>
  <a href="https://github.com/seguidodoblado/comic-identify/blob/main/COPYING"><img src="https://img.shields.io/github/license/seguidodoblado/comic-identify" alt="license"></a>
  <a href="https://github.com/seguidodoblado/comic-identify/commits/main/"><img src="https://img.shields.io/github/last-commit/seguidodoblado/comic-identify" alt="last commit"></a>
  <a href="https://github.com/seguidodoblado/comic-identify/commits/main/"><img src="https://img.shields.io/github/commit-activity/t/seguidodoblado/comic-identify" alt="total commits"></a>
  <a href="https://github.com/seguidodoblado/comic-identify/releases"><img src="https://img.shields.io/github/downloads/seguidodoblado/comic-identify/total" alt="downloads"></a>
  <a href="https://github.com/seguidodoblado/comic-identify/stargazers"><img src="https://img.shields.io/github/stars/seguidodoblado/comic-identify?style=flat" alt="stars"></a>
  <a href="https://github.com/seguidodoblado/comic-identify/issues"><img src="https://img.shields.io/github/issues/seguidodoblado/comic-identify" alt="issues"></a>
  <a href="https://github.com/seguidodoblado/comic-identify"><img src="https://img.shields.io/github/languages/top/seguidodoblado/comic-identify" alt="language"></a>
  <a href="https://codetime.dev"><img alt="CodeTime Badge" src="https://shields.jannchie.com/endpoint?style=flat&color=0284c7&url=https%3A%2F%2Fcodetime.dev%2Fv3%2Fusers%2Fshield%3Fuid%3D36830"></a>
  <a href="https://wakatime.com/badge/github/seguidodoblado/comic-identify"><img src="https://wakatime.com/badge/github/seguidodoblado/comic-identify.svg" alt="wakatime"></a>
</p>

<p align="center">
  Identifica y cataloga tu colección de cómics digitales (CBR, CBZ, CB7) por portada o por título, con
  Grand Comics Database, Universo Marvel, Tebeosfera y ComicVine.
</p>

<p align="center">
  <img src="docs/screenshot.png" alt="Captura de Comic Identify">
</p>

Aplicación de escritorio (GTK 4 + PyGObject, interfaz en español e inglés), de uso personal: sin servidor ni cuenta,
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

## Datos de terceros

Los datos de GCD son © Grand Comics Database (<https://www.comics.org/>) y se distribuyen bajo
licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). El índice local que genera
la aplicación es una obra derivada y debe conservar esa atribución y licencia si se comparte.

Los datos de las fichas de [Universo Marvel](https://fichas.universomarvel.com/) pertenecen a sus autores, y los
personajes y publicaciones a sus titulares. La base local es para tu uso personal: no la redistribuyas.

Los datos de [Tebeosfera](https://www.tebeosfera.com/) son de la Asociación Cultural Tebeosfera y de sus
colaboradores (sus textos se distribuyen con licencia CC BY-SA 4.0 y las imágenes son de sus titulares). La base
local es para tu uso personal.

Los datos de [Comic Vine](https://comicvine.gamespot.com/) se obtienen a través de su API pública; sus términos de
uso exigen enlazar de vuelta a su web en cualquier página que use sus datos.

## Privacidad

Comic Identify no tiene servidor ni cuenta propios y no recoge datos. Qué se guarda, dónde y con quién se comunica está en la **[política de privacidad](PRIVACY.md)**.

## Licencia

Este proyecto se distribuye bajo la GNU General Public License, versión 3 o posterior (ver `COPYING`).
