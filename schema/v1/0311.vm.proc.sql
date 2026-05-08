CREATE OR REPLACE PROCEDURE core.insert_minimal_vm(
    p_vm_name VARCHAR(255),
    p_ipv4 VARCHAR(55)
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO core.vms (vm_name, ipv4)
    VALUES (p_vm_name, p_ipv4);
END;
$$;