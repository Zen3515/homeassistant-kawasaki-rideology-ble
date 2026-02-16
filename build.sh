#! /bin/bash

rm kawasaki.zip; cd custom_components/kawasaki && zip -r ../../kawasaki.zip .; cd ../..; unzip -l kawasaki.zip
