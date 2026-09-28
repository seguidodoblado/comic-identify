#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
stage="$base/.deb-stage"
version=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$base/pyproject.toml")
package="$base/../comic-identify_${version}-1_all.deb"
command -v dpkg-deb >/dev/null 2>&1 || { echo "Falta dpkg-deb (instala dpkg-dev)." >&2; exit 1; }
rm -rf "$stage"
mkdir -p "$stage/DEBIAN" "$stage/opt/comic-identify" "$stage/usr/bin" "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/scalable/apps"
cp -a "$base/src/comic_identify" "$stage/opt/comic-identify/"
cp "$base/comic-identify.svg" "$stage/opt/comic-identify/"
find "$stage/opt/comic-identify" -type d -name __pycache__ -prune -exec rm -rf {} +
cp "$base/debian/comic-identify-launcher" "$stage/usr/bin/comic-identify"
cp "$base/debian/comic-identify.desktop" "$stage/usr/share/applications/"
cp "$base/comic-identify.svg" "$stage/usr/share/icons/hicolor/scalable/apps/"
cp "$base/debian/postinst" "$stage/DEBIAN/postinst"
cat > "$stage/DEBIAN/control" <<EOT
Package: comic-identify
Version: ${version}-1
Section: graphics
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-4.0, python3-pil, python3-numpy, zbar-tools
Recommends: unrar | p7zip-full, gir1.2-webkit-6.0, gir1.2-vte-3.91
Suggests: rar, p7zip-full
Maintainer: Jose Antonio Seguido Doblado <jose.antonio.seguido@gmail.com>
Homepage: https://github.com/seguidodoblado/comic-identify
Description: Identifica un cómic a partir de su portada
 Aplicación GTK para gestionar una colección de cómics digitales: identifica por
 portada o título (Grand Comics Database, Universo Marvel, código de barras,
 ComicVine y comparación visual de portadas), normaliza nombres, escribe metadatos
 ComicInfo.xml, transfiere a GCstar, hace copias de seguridad y ofrece un
 asistente de IA opcional con tu propia sesión.
EOT
chmod 755 "$stage/usr/bin/comic-identify"
chmod 755 "$stage/DEBIAN/postinst"
dpkg-deb --build --root-owner-group "$stage" "$package"
rm -rf "$stage"
echo "Paquete generado: $package"
