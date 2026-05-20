package main

import (
	"fmt"
)

func main() {
	vms, err := readCSV("hosts.csv")
	if err != nil {
		fmt.Println("Error reading CSV.." + err.Error())
		return
	}

	for _, vm := range vms[0:] {
		err := scanVM(&vm)
		if err != nil {
			fmt.Println("Error reading CSV.." + err.Error())
			return
		}
	}
}
