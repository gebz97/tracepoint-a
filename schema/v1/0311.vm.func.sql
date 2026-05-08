CREATE OR REPLACE FUNCTION core.insert_minimal_vm(
    p_vm_name VARCHAR(255),
    p_ipv4 VARCHAR(55)
)
RETURNS core.vms
LANGUAGE plpgsql
AS $$
DECLARE
    v_result core.vms%ROWTYPE;
BEGIN
    -- Insert only the required NOT NULL columns
    INSERT INTO core.vms (
        vm_name,
        ipv4
    ) VALUES (
        p_vm_name,
        p_ipv4
    )
    RETURNING * INTO v_result;
    
    RETURN v_result;
END;
$$;