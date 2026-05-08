-- =============================================================================
-- HYPERVISOR HOSTS VIEW
-- =============================================================================
CREATE
OR REPLACE VIEW core.vw_hypervisor_hosts AS
SELECT
    hh.id AS host_id,
    hh.hostname,
    hh.ipv4,
    hh.ipmi_ip,
    hh.hypervisor_version,
    hh.platform_ref AS host_platform_ref,
    hh.manufacturer,
    hh.model,
    hh.serial_number,
    hh.cpu_model,
    hh.cpu_sockets,
    hh.cpu_cores,
    hh.cpu_sockets * hh.cpu_cores AS total_cores,
    hh.memory_mb,
    hh.maintenance_mode,
    hh.metadata AS host_metadata,
    hh.created_at AS host_created_at,
    hh.updated_at AS host_updated_at,
    ht.name AS hypervisor_type,
    pv.name AS platform_vendor,
    hs.name AS host_status,
    -- cluster
    cl.id AS cluster_id,
    cl.cluster_name,
    cl.high_availability AS cluster_ha,
    cl.load_balancing AS cluster_lb,
    ct.name AS cluster_type,
    -- datacenter
    dc.id AS datacenter_id,
    dc.datacenter_name,
    dc.location AS datacenter_location,
    -- vm counts
    (
        SELECT
            count(*)
        FROM
            core.vms v
        WHERE
            v.hypervisor_host_id = hh.id
    ) AS vm_count,
    (
        SELECT
            count(*)
        FROM
            core.vms v
            JOIN core.power_states ps ON ps.id = v.power_state_id
        WHERE
            v.hypervisor_host_id = hh.id
            AND ps.name = 'running'
    ) AS running_vm_count
FROM
    core.hypervisor_hosts hh
    LEFT JOIN core.hypervisor_types ht ON ht.id = hh.hypervisor_type_id
    LEFT JOIN core.platform_vendors pv ON pv.id = hh.platform_vendor_id
    LEFT JOIN core.host_statuses hs ON hs.id = hh.status_id
    LEFT JOIN core.clusters cl ON cl.id = hh.cluster_id
    LEFT JOIN core.cluster_types ct ON ct.id = cl.cluster_type_id
    LEFT JOIN core.datacenters dc ON dc.id = cl.datacenter_id;