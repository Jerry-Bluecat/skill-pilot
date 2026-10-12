#!/bin/sh
/usr/bin/nohup /Users/j/.nvm/versions/node/v24.21.0/bin/node /Users/j/Developer/skill-pilot/scripts/m7-launch-browser.cjs "$1" >> "$M7_BROWSER_RUNTIME/browser.log" 2>&1 < /dev/null &
exit 0
