for variable in 1 2 3 4 5 6 7 8 9 10 

do
	echo $variable
	python toggle_thresholds.py --save_progress
done
