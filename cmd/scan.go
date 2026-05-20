package main

import (
	"errors"
	"fmt"
)

func scanVM(v *VM) error {
	if v.Host == "" {
		return errors.New("VM Host empty")
	}
	fmt.Println(v.Host)
	return nil
}