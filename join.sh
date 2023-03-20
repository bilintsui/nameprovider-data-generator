#! /bin/bash
join col1.txt col2.txt -t $'\t' | join - col3.txt -t $'\t' | join - col4.txt -t $'\t' | sed 's/"\t"/", "/g' | awk -F '\t' '{print "\t[\""$1"\"] = { "$2" },"}' | sed -e "s/\[\"/['/" -e "s/\"\]/']/" > tmp.txt
