#!/bin/sh
NMAP_FILE=nmap.grep

egrep -v "^#|Status: Up" $NMAP_FILE | cut -d' ' -f4- | \
sed -n -e 's/Ignored.*//p' | tr ',' '\n' | sed -e 's/^[ \t]*//' | \
sort -n | uniq -c | sort -k 1 -r | head -n 10