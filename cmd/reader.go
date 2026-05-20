package main

import (
	"encoding/csv"
	"os"
)

func readCSV(path string) ([]VM, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	rows, err := csv.NewReader(f).ReadAll()
	if err != nil {
		return nil, err
	}

	records := make([]VM, 0, len(rows)-1)
	for _, row := range rows[1:] {
		records = append(records, VM{
			Host: row[0],
		})
	}
	return records, nil
}
