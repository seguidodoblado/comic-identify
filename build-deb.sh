#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
stage="$base/.deb-stage"
version=$(sed -n '1s/^[^ ]* (\([^)]*\)).*/\1/p' "$base/debian/changelog")
test -n "$version" || { echo "No se pudo leer la versión de debian/changelog" >&2; exit 1; }
upstream=${version%-*}
project_version=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$base/pyproject.toml")
init_version=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$base/src/comic_identify/__init__.py")
test "$upstream" = "$project_version" -a "$upstream" = "$init_version" || { echo "Versiones distintas: debian/changelog ($upstream), pyproject.toml ($project_version), __init__.py ($init_version). Ejecuta «Versionar repositorio»." >&2; exit 1; }
package="$base/../comic-identify_${version}_all.deb"
command -v dpkg-deb >/dev/null 2>&1 || { echo "Falta dpkg-deb (instala dpkg-dev)." >&2; exit 1; }
rm -rf "$stage"
doc="$stage/usr/share/doc/comic-identify"
mkdir -p "$stage/DEBIAN" "$stage/usr/share/comic-identify" "$stage/usr/bin" "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/scalable/apps" "$doc"
cp -a "$base/src/comic_identify" "$stage/usr/share/comic-identify/"
cp "$base/comic-identify.svg" "$stage/usr/share/comic-identify/"
find "$stage/usr/share/comic-identify" -type d -name __pycache__ -prune -exec rm -rf {} +
cp "$base/debian/comic-identify-launcher" "$stage/usr/bin/comic-identify"
cp "$base/debian/comic-identify.desktop" "$stage/usr/share/applications/"
cp "$base/comic-identify.svg" "$stage/usr/share/icons/hicolor/scalable/apps/"
cp "$base/debian/copyright" "$doc/copyright"
gzip -9n -c "$base/debian/changelog" > "$doc/changelog.Debian.gz"
# Páginas de manual (inglés en man1, español en es/man1); la versión se rellena aquí
mkdir -p "$stage/usr/share/man/man1" "$stage/usr/share/man/es/man1"
sed "s/@VERSION@/${version}/" "$base/debian/comic-identify.1" | gzip -9n > "$stage/usr/share/man/man1/comic-identify.1.gz"
sed "s/@VERSION@/${version}/" "$base/debian/comic-identify.es.1" | gzip -9n > "$stage/usr/share/man/es/man1/comic-identify.1.gz"
cp "$base/debian/postinst" "$stage/DEBIAN/postinst"
# Permisos fijos (no dependen de la umask de quien construye): 755 en directorios, 644 en ficheros
find "$stage" -type d -exec chmod 755 {} +
find "$stage" -type f -exec chmod 644 {} +
cat > "$stage/DEBIAN/control" <<EOT
Package: comic-identify
Version: ${version}
Section: graphics
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-4.0, python3-pil, python3-numpy, zbar-tools
Recommends: unrar | p7zip-full, gir1.2-webkit-6.0, gir1.2-vte-3.91
Suggests: rar, p7zip-full
Maintainer: Jose Antonio Seguido Doblado <jose.antonio.seguido@gmail.com>
Homepage: https://github.com/seguidodoblado/comic-identify
Description: Identifica un cómic a partir de su portada
 Aplicación GTK para gestionar una colección de cómics digitales:
 identifica por portada o título (Grand Comics Database, Universo Marvel,
 Tebeosfera, código de barras, ComicVine y comparación visual de portadas),
 normaliza nombres, escribe metadatos ComicInfo.xml, transfiere a GCstar,
 hace copias de seguridad y ofrece un asistente de IA opcional con tu
 propia sesión.
EOT
chmod 644 "$stage/DEBIAN/control"
chmod 755 "$stage/usr/bin/comic-identify"
chmod 755 "$stage/DEBIAN/postinst"
(cd "$stage" && find . -type f ! -path './DEBIAN/*' -printf '%P\n' | LC_ALL=C sort | xargs -d '\n' md5sum > DEBIAN/md5sums)
chmod 644 "$stage/DEBIAN/md5sums"
dpkg-deb --build --root-owner-group "$stage" "$package"
rm -rf "$stage"
echo "Paquete generado: $package"
