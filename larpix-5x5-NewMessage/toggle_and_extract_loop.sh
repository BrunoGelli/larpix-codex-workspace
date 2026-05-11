for variable in 1 2 3 
do
	echo $variable
	# check where the thresholds are and iterate towards desired point
	python extract_thresholds_and_toggle.py	

	# test data rate and make sure its not diverging
	python record_data.py --tag rate_check --file_count 1 --runtime 20

done
