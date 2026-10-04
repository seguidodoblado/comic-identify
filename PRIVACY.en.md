<p align="right"><a href="PRIVACY.md">🇪🇸 Español</a></p>

# Privacy Policy

Last updated: October 5, 2026.

Comic Identify is a desktop application for personal use. It has no server or account of its own, and its
author does not receive any data from the people who use it.

## What data it handles

- **Your comic collection:** the paths of the folders you choose, file names, covers (to compute their visual
  fingerprint and read the barcode) and the `ComicInfo.xml` metadata that the application writes into your files.
- **Your settings:** folders, naming pattern, AI assistant command, backup folder and, if you set it, your
  ComicVine API key.
- **Undo logs** for renames, metadata and GCstar transfers.

## Where it is stored

Everything stays on your computer, in the user's XDG directories:

- `~/.config/comic-identify/config.json`: settings and ComicVine key (in clear text, protected by 600 permissions).
- `~/.local/share/comic-identify/`: local indexes (collection, Grand Comics Database, Universo Marvel and
  Tebeosfera), undo logs and your own logos.
- `~/.cache/comic-identify/`: downloaded logos and icons, web panel cache and the assistant's working folder.
- Backups, in the folder you choose.

## Who it is shared with

No one, on the application's part. It includes no analytics, telemetry or advertising. The network is only
used when you ask for it, and requests go from your computer to:

- **Grand Comics Database** (comics.org), **Universo Marvel**, **Tebeosfera** and **ComicVine**, to search and
  download records. ComicVine receives your API key and the search text. The others receive the query or the
  record's address.
- The search and shopping websites you open from the application, in the built-in web panel or in your
  browser. Those sites have their own policies; the application blocks Tebeosfera's measurement and
  advertising in the panel, and does not store cookies on disk except comics.org's access cookie, only in memory.
- **The AI assistant is optional and uses your own session.** If you enable it, the application runs the
  command you configure (by default, `claude`) with a message and the path of the cover. What that program
  sends to its own service is governed by its own policy, not this one.

The covers of your files are not sent to any server of the application, which does not exist.

## How to delete your data

Remove `~/.config/comic-identify/`, `~/.local/share/comic-identify/` and `~/.cache/comic-identify/`, and any
backups you created. The `ComicInfo.xml` metadata written into your files can be undone from Settings before
deleting the logs. Uninstalling the application does not delete that data by itself.

## Changes to this policy

If it changes, this document and the date above will be updated; the history is in the repository.

## Contact

Jose Antonio Seguido Doblado · jose.antonio.seguido@gmail.com
