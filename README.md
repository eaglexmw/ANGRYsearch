# ANGRYsearch
Linux file search, instant results as you type

PyQt4 version

This is lighter, faster to index version, results are not in table but simple list.
Only full path is displayed, no size, no date, no icons for various file types.


![alt tag](http://i.imgur.com/H7ptdGG.gif)

### How to make it work on your system:

**dependencies** - `python-pyqt4`, `libxkbcommon-x11`, `xdg-utils`

download the latest pyqt4 release of ANGRYsearch, unpack it, go in to the containing directory
* **if you just want to test it, you can run it right away**
  * `python3 angrysearch.py`
  * once you are done testing, remember to remove the database that is created in
    `~/.cache/angrysearch/angry_database.db`

for a long term usage on your system you need to find some place for it,
lets say /opt/angrysearch, copy all the files there, make the main one executable,
and make some links to these files to integrate ANGRYsearch in to your system well.

* create angrysearch folder in /opt

        sudo mkdir /opt/angrysearch

* go where you extracted the latest release, go deeper inside, copy all the files to /opt/angrysearch

        sudo cp -r * /opt/angrysearch

* make the main python file executable

        sudo chmod +x /opt/angrysearch/angrysearch.py

* make a link in /usr/share/applications to the desktop file so that angrysearch appears in your launchers and start menus

        sudo ln -s /opt/angrysearch/angrysearch.desktop /usr/share/applications

* would be nice if it would have some distinguishable icon, make a link to the icon

        sudo ln -s /opt/angrysearch/icons/angrysearch.svg /usr/share/pixmaps

* to be able to run angrysearch from terminal anywhere by just writing `angrysearch` , make this link

        sudo ln -s /opt/angrysearch/angrysearch.py /usr/bin/angrysearch
