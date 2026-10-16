# Nimble Notes

NimbleCloud13 - nimblecloud13@gmail.com - https://github.com/nimblecloud13

One note per app, in a small desktop window you can leave open all day.

It is a native Windows window, not a browser page. There is no server and no port, nothing is
downloaded and nothing leaves this computer. With the window open it holds about 45 MB of memory and
uses no CPU while idle. Hidden in the tray it hands most of that back to Windows.

## A quick look

![One note per project, always open](docs/intro_0_hero.png)

![Revisions complete: finish a batch, keep the history](docs/intro_1_revisions.png)

![Categories that nest, pins, and groups](docs/intro_2_categories.png)

![Pictures and videos inside the note](docs/intro_3_pictures.png)

![Snap it to the side of the screen and pin it](docs/intro_4_place.png)

![Fork a note into a _v2](docs/intro_5_fork.png)

![Fourteen themes](docs/intro_6_themes.png)

![Three steps to get it](docs/intro_7_get_it.png)

The same tour as a page: open `Nimble_Notes_Intro.html` in a browser.

## Run it

1. `install.bat` (once). Creates `.venv` and installs the Qt toolkit.
2. `launch_nimble_notes.bat`. The window opens and an amber icon appears in the tray.

The X hides the window; the app keeps running in the tray. Click the tray icon to bring it back,
right-click it for **Quit**. Launching it a second time shows the window that is already running.
`.venv\Scripts\pythonw.exe app.py --quit` asks the running copy to save and close.

## The window

- **Left column**: every note, under its category. Drag a row to reorder it or move it into another
  category. Right-click a row for rename, Fork, pin, folder, move and remove. Click a category to fold
  it. Under the search box: **+ Category**, **Families**, and **Groups** with one button per group and
  **All notes**. The note you are on is lit in a lighter navy; a note with open lines has an amber
  wash and an amber bar, and is lit gold when it is the one you are on.
- **Names come first.** When the list gets narrow, the tags on a row go before any letter of the
  name is cut.
- **TL;DR box**: what the app is for. One line tall when empty, growing with its text.
- **Ideas box**: half-thoughts that are not revision notes yet, in a lighter gold and a little larger
  than the notes. Saved as `ideas.txt` in the entry's folder.
- **Notes pane**: your notes for that app. The gold number on its label row is the size, in tokens,
  of what you are writing.

Everything saves by itself about a second after you stop typing.

| Keys | Does |
| --- | --- |
| Ctrl+Enter | Revisions complete: grey out everything typed and file it as the next revision |
| Ctrl+D | Tick off the current line (or every selected line), or bring it back |
| Ctrl+Z / Ctrl+Y | Undo or redo moving a note (in the text boxes they undo and redo typing) |
| Ctrl + and Ctrl - | Notes text bigger or smaller; Ctrl+0 resets. Ctrl with the mouse wheel works too |
| Ctrl+F | Search names, family, TL;DR, ideas and note text. Esc clears it |
| Ctrl+N | New note under the current one |
| Ctrl+G | Switch the list between the last group shown and every note |
| F2 | Rename the current note (or double-click its name) |
| Del | Remove the note selected in the list (a toast offers Undo) |
| Mouse back / forward | Walk through the notes you visited |

## New notes

**+ New** (or Ctrl+N) adds a note with its name ready to type. Press Enter after the name and the
cursor goes to the notes. A new note that is left blank is not kept.

## Revisions complete

The notes pane reads top to bottom: the text you are typing, the picture strip, the **Revisions
complete** button, then everything finished so far, greyed out, newest first, each batch under a tag
with its number, date and time.

Press the button (or Ctrl+Enter) when a batch is done. It is greyed out and filed as the next
revision, and the space above is cleared. A toast offers Undo. What was completed is also copied to
the clipboard: the note's name, a blank line, then the text. When the revision has pictures, each
picture is copied first, one at a time, so Windows clipboard history (Win+V) holds every one, and
the text is copied last so a plain Ctrl+V pastes the text.

Each revision's tag ends in **Undo**: click it and that revision becomes editable again where it
is. Its tag then reads **Revisions complete**; click it when you are done.

Ctrl+D greys single lines inside the text you are still working on.

## Categories

A new list starts with:

    Incoming
      High Priority
        Medium
          Low
    Work
    Projects
    Calls
    Team
    Vibe Coded
    Other

- **Fold**: click a category to hide everything inside it; click again to show it.
- **Move notes**: drag a note into another category, or right-click it and use **Move to**.
  Ctrl+Z puts it back, Ctrl+Y moves it again.
- **Move categories**: drag a heading. Dropped right under another heading it goes inside that
  category; dropped anywhere else it goes after the category above. Everything inside it comes along.
- **Right-click a category** to sort its notes, sort the categories beside it, fold, pin, rename,
  add a subcategory, move it, or remove it (its notes go to the category above, with Undo).

Notes sort by My order, A to Z, Z to A, Oldest first, Newest first, Recently edited or Family. Each
category keeps its own choice, shown in small amber text on its heading.

**Pins**: every row has a small pin at its right end. A pinned note stays at the top of its
category; a pinned category stays first among the categories beside it.

## Fork

**Fork**, beside the note's name (or right-click a row), makes a copy right below it named `_v2`, or
the next free number. The copy has the notes, ideas, TL;DR, family, folder, launcher, groups and
pictures.

## Settings and fonts

The gear at the bottom left opens **Settings**, with two lists: **App font** (the list, buttons and
labels) and **Notes font** (the notes and the Ideas box). Every name is written in its own font. A
click uses it at once, and it is kept after a restart.

| From | Fonts |
| --- | --- |
| Windows | Segoe UI (the default), Arial, Calibri, Verdana, Tahoma, Trebuchet MS, Georgia, Cambria, Times New Roman, Consolas |
| Google Fonts | Inter, Roboto, Open Sans, Lato, Poppins, Nunito, Source Sans 3, IBM Plex Sans, Work Sans, JetBrains Mono, Montserrat, Red Hat Display |
| Fontshare | Supreme, Author, Satoshi, Pilcrow Rounded, Bespoke Serif, Tabular |

The Google fonts are in `fonts/` under the SIL Open Font License. The Fontshare fonts are free to
use but their license does not allow passing the files on, so they are not in this repository: get
them from fontshare.com and put each family's .otf files in `fonts/<name>/` (for example
`fonts/satoshi/`). A font whose files are missing is left out of the lists.

## Placing the window

**Place**, in the status bar, opens a grid of little screens: half, third and quarter against any
side, and the four corners. Click one and the window takes that part of the screen, like
Windows+arrow keys, and comes back there after a restart. **Full screen** and **Move to the next
screen** are in the same menu.

**Pin**: when the window is docked to a half, a third or a quarter against a side, a **Pin** button
shows on the header row. Pinned, that strip of the screen is reserved the way the taskbar is: other
windows keep out of it.

A small window tightens its layout, and below about 380 px wide it shows one pane at a time with a
**List** button.

## Themes

**Theme**, beside Place, offers 14 themes: Nimble (the default), Cream, Fog, Deep Sea, Furnace, Coal,
Forest, Moss, Orchid, Blush, Graphite, Carbon, Steel and Espresso. Point at a name to see the app in
it; click to keep it. The tray menu has the same list.

## Groups

A group is a short list of notes to work on together. A note can be in several groups.

- **See a group**: click its button above the list (it lights gold). **All notes** shows everything
  and is lit while it is what the list shows. Ctrl+G flips between the two.
- **Make a group**: **+ New** beside the Groups label, type its name, click the notes that belong in
  it, then **Done**.
- **Change a group**: **Edit** (or right-click its button). Rename, delete, add and take out notes,
  add a whole section, or add every note with open lines. **Undo** steps back through the changes.
- A note in a group wears the group's name as a small tag on its row and a **Group:** chip under its
  title; click the chip to tick it in or out of any group.

## Families

A family is a tag shared by apps that do the same job. **Families**, under the search box, manages
them in one place: tick entries in or out, rename or merge a family, delete it, or start a new one.
The Family chip beside a note's name sets one note's family.

## Pictures and videos

Add them with the button at the left of the strip, by dragging files onto the note, or with Ctrl+V.
Each is copied into `images/<note name>/`; the original is never touched. They belong to the batch
they were added to and are filed with it.

Click a thumbnail to enlarge it: arrows step through, the wheel zooms, Esc closes, **Copy image**
copies it. The small x on a thumbnail takes the picture off the note after showing where the file
lives. The app never deletes anything from the images folder, and says so each time that folder
passes another 5 GB.

## Copy note and the token count

**Copy note** puts the whole note on the clipboard: the name, the open text, then every revision under
its number and date. The gold number beside it counts the tokens in what you are writing.

## Open folder and Launch

**Open folder** opens the app's folder in Explorer, **Change linked folder** picks another one, and
**Launch** runs the app's launch file as a double-click would (it looks for `launch_<name>.bat`,
`launch.bat`, `run.bat`, `start*.bat`, a .bat or .exe named after the folder). **Link launcher**
points it at any file.

## Where things are saved

| File | Holds |
| --- | --- |
| `notes/<Name>/<Name>.txt` | The notes for one entry, as plain text |
| `notes/<Name>/ideas.txt` | That entry's Ideas box |
| `images/<Name>/` | Every picture and video added to that entry |
| `data/apps.json` | The list: names, categories, families, folders, launch files, TL;DRs |
| `data/state.json` | Window place, theme, fonts, sort choices, groups, text size |
| `data/removed/` | Removed entries; right-click the list for Restore removed |

A notes file is the open text first, then each revision under a line of its own, newest first:

    still to do
    - [x] a line ticked off with Ctrl+D
    --- Revision 2 | 10-10-26 20:31 ---
    the second batch

    --- Revision 1 | 10-10-26 18:02 ---
    the first batch

Pictures are listed at the end of the part they belong to: `[image] screenshot.png` or
`[video] clip.mp4`. The files can be edited while the app is open; it picks the change up the next
time its window is clicked. Folders under your home directory are stored as `~/...`.

## Start with Windows

The first launch adds a startup entry so Nimble Notes starts hidden in the tray when you sign in.
Turn it off or on from the tray menu.

## Files

- `app.py` - the window, tray icon and startup
- `store.py` - reading and writing the files in `data/`
- `media.py` - the picture strip, the enlarged picture view, the small pop-up, the resize grip
- `theme.py` - the stylesheet, built from the theme picked
- `nimble_themes.py` - the 14 themes
- `fonts/` - the bundled fonts and `fonts.json`, the list the Settings card reads

## Links

**NimbleCloud13**, beside the version number at the bottom left, opens links to GitHub
(github.com/nimblecloud13) and Buy me a coffee (buymeacoffee.com/nimblecloud13).
