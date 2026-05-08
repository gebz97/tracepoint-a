-- =============================================================================
-- FULL VM VIEW
-- =============================================================================

CREATE OR REPLACE VIEW core.vw_vms AS
SELECT
    -- vm core
    v.id                        AS vm_id,
    v.vm_name,
    v.ipv4,
    v.service                   AS vm_service_tag,
    v.distribution,
    v.os_version,
    v.os_major,
    v.platform_ref              AS vm_platform_ref,
    v.cpus,
    v.memory_mb,
    v.storage_total_gb,
    v.metadata                  AS vm_metadata,
    v.created_at                AS vm_created_at,
    v.updated_at                AS vm_updated_at,

    -- lookups
    ps.name                     AS power_state,
    e.name                      AS environment,
    a.name                      AS arch,

    -- org: service
    svc.id                      AS service_id,
    svc.service_name,

    -- org: team (direct on vm, may differ from service's team)
    tm.id                       AS team_id,
    tm.team_name,
    tm.email                    AS team_email,

    -- org: service's team
    stm.id                      AS service_team_id,
    stm.team_name               AS service_team_name,

    -- org: project
    pr.id                       AS project_id,
    pr.project_name,
    pr.start_date               AS project_start_date,
    pr.end_date                 AS project_end_date,

    -- org: cost center
    cc.id                       AS cost_center_id,
    cc.cost_center_code,
    cc.cost_center_name,

    -- hypervisor host
    hh.id                       AS hypervisor_host_id,
    hh.hostname                 AS hypervisor_hostname,
    hh.ipv4                     AS hypervisor_ipv4,
    hh.ipmi_ip                  AS hypervisor_ipmi_ip,
    hh.hypervisor_version,
    hh.manufacturer             AS host_manufacturer,
    hh.model                    AS host_model,
    hh.serial_number            AS host_serial_number,
    hh.cpu_model                AS host_cpu_model,
    hh.cpu_sockets              AS host_cpu_sockets,
    hh.cpu_cores                AS host_cpu_cores,
    hh.memory_mb                AS host_memory_mb,
    hh.maintenance_mode         AS host_maintenance_mode,
    hh.platform_ref             AS host_platform_ref,
    ht.name                     AS hypervisor_type,
    pv.name                     AS platform_vendor,
    hs.name                     AS host_status,

    -- cluster
    cl.id                       AS cluster_id,
    cl.cluster_name,
    cl.high_availability        AS cluster_ha,
    cl.load_balancing           AS cluster_lb,
    clt.name                    AS cluster_type,

    -- datacenter
    dc.id                       AS datacenter_id,
    dc.datacenter_name,
    dc.location                 AS datacenter_location,

    -- compute pool
    cp.id                       AS compute_pool_id,
    cp.pool_name                AS compute_pool_name,
    cp.cpu_shares               AS pool_cpu_shares,
    cp.cpu_limit_mhz            AS pool_cpu_limit_mhz,
    cp.mem_shares               AS pool_mem_shares,
    cp.mem_limit_mb             AS pool_mem_limit_mb,

    -- template
    t.id                        AS template_id,
    t.template_name,
    t.distribution              AS template_distribution,
    t.os_version                AS template_os_version

FROM core.vms v
LEFT JOIN core.power_states       ps  ON ps.id   = v.power_state_id
LEFT JOIN core.environments       e   ON e.id    = v.environment_id
LEFT JOIN core.cpu_archs          a   ON a.id    = v.arch_id
LEFT JOIN core.services           svc ON svc.id  = v.service_id
LEFT JOIN core.teams              tm  ON tm.id   = v.team_id
LEFT JOIN core.teams              stm ON stm.id  = svc.team_id
LEFT JOIN core.projects           pr  ON pr.id   = v.project_id
LEFT JOIN core.cost_centers       cc  ON cc.id   = v.cost_center_id
LEFT JOIN core.hypervisor_hosts   hh  ON hh.id   = v.hypervisor_host_id
LEFT JOIN core.hypervisor_types   ht  ON ht.id   = hh.hypervisor_type_id
LEFT JOIN core.platform_vendors   pv  ON pv.id   = hh.platform_vendor_id
LEFT JOIN core.host_statuses      hs  ON hs.id   = hh.status_id
LEFT JOIN core.clusters           cl  ON cl.id   = hh.cluster_id
LEFT JOIN core.cluster_types      clt ON clt.id  = cl.cluster_type_id
LEFT JOIN core.datacenters        dc  ON dc.id   = cl.datacenter_id
LEFT JOIN core.compute_pools      cp  ON cp.id   = v.compute_pool_id
LEFT JOIN core.templates          t   ON t.id    = v.template_id;


-- =============================================================================
-- VM DISKS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW core.vw_vm_disks AS
SELECT
    vd.id                       AS disk_id,
    vd.label                    AS disk_label,
    vd.size_gb                  AS disk_size_gb,
    vd.disk_path,
    vd.boot_disk,
    vd.created_at               AS disk_created_at,
    vd.updated_at               AS disk_updated_at,
    df.name                     AS disk_format,

    -- vm
    v.id                        AS vm_id,
    v.vm_name,
    v.ipv4                      AS vm_ipv4,
    e.name                      AS environment,
    ps.name                     AS power_state,

    -- datastore
    ds.id                       AS datastore_id,
    ds.datastore_name,
    ds.ds_path                  AS datastore_path,
    ds.total_gb                 AS datastore_total_gb,
    ds.used_gb                  AS datastore_used_gb,
    ds.free_gb                  AS datastore_free_gb,
    dst.name                    AS datastore_type,

    -- datacenter (via datastore)
    dc.id                       AS datacenter_id,
    dc.datacenter_name

FROM core.vm_disks vd
LEFT JOIN core.disk_formats       df  ON df.id  = vd.disk_format_id
LEFT JOIN core.vms                v   ON v.id   = vd.vm_id
LEFT JOIN core.power_states       ps  ON ps.id  = v.power_state_id
LEFT JOIN core.environments       e   ON e.id   = v.environment_id
LEFT JOIN core.datastores         ds  ON ds.id  = vd.datastore_id
LEFT JOIN core.datastore_types    dst ON dst.id = ds.datastore_type_id
LEFT JOIN core.datacenters        dc  ON dc.id  = ds.datacenter_id;


-- =============================================================================
-- VM NICS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW core.vw_vm_nics AS
SELECT
    vn.id                       AS nic_id,
    vn.mac_address,
    vn.ipv4                     AS nic_ipv4,
    vn.ipv6                     AS nic_ipv6,
    vn.connected,
    vn.created_at               AS nic_created_at,
    vn.updated_at               AS nic_updated_at,
    at.name                     AS adapter_type,

    -- vm
    v.id                        AS vm_id,
    v.vm_name,
    v.ipv4                      AS vm_ipv4,
    e.name                      AS environment,
    ps.name                     AS power_state,

    -- network
    n.id                        AS network_id,
    n.network_name,
    n.vlan_id,
    n.cidr,
    n.gateway,
    n.virtual_switch,
    nt.name                     AS network_type

FROM core.vm_nics vn
LEFT JOIN core.adapter_types      at  ON at.id  = vn.adapter_type_id
LEFT JOIN core.vms                v   ON v.id   = vn.vm_id
LEFT JOIN core.power_states       ps  ON ps.id  = v.power_state_id
LEFT JOIN core.environments       e   ON e.id   = v.environment_id
LEFT JOIN core.networks           n   ON n.id   = vn.network_id
LEFT JOIN core.network_types      nt  ON nt.id  = n.network_type_id;


-- =============================================================================
-- VM SNAPSHOTS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW core.vw_vm_snapshots AS
SELECT
    s.id                        AS snapshot_id,
    s.snapshot_name,
    s.description               AS snapshot_description,
    s.size_gb                   AS snapshot_size_gb,
    s.quiesced,
    s.platform_ref              AS snapshot_platform_ref,
    s.created_at                AS snapshot_created_at,

    -- parent snapshot
    sp.id                       AS parent_snapshot_id,
    sp.snapshot_name            AS parent_snapshot_name,

    -- vm
    v.id                        AS vm_id,
    v.vm_name,
    v.ipv4                      AS vm_ipv4,
    ps.name                     AS power_state,
    e.name                      AS environment

FROM core.vm_snapshots s
LEFT JOIN core.vm_snapshots       sp  ON sp.id  = s.parent_id
LEFT JOIN core.vms                v   ON v.id   = s.vm_id
LEFT JOIN core.power_states       ps  ON ps.id  = v.power_state_id
LEFT JOIN core.environments       e   ON e.id   = v.environment_id;


-- =============================================================================
-- DATASTORES VIEW
-- =============================================================================

CREATE OR REPLACE VIEW core.vw_datastores AS
SELECT
    ds.id                       AS datastore_id,
    ds.datastore_name,
    ds.ds_path,
    ds.total_gb,
    ds.used_gb,
    ds.free_gb,
    ROUND(ds.used_gb * 100.0 / NULLIF(ds.total_gb, 0), 2)
                                AS used_pct,
    ds.thin_provisioned,
    ds.replication_enabled,
    ds.platform_ref             AS datastore_platform_ref,
    ds.metadata                 AS datastore_metadata,
    ds.created_at               AS datastore_created_at,
    ds.updated_at               AS datastore_updated_at,
    dst.name                    AS datastore_type,

    -- datacenter
    dc.id                       AS datacenter_id,
    dc.datacenter_name,
    dc.location                 AS datacenter_location,

    -- mounted host count
    (
        SELECT count(*)
        FROM core.datastore_hosts dh
        WHERE dh.datastore_id = ds.id
    )                           AS mounted_host_count

FROM core.datastores ds
LEFT JOIN core.datastore_types    dst ON dst.id = ds.datastore_type_id
LEFT JOIN core.datacenters        dc  ON dc.id  = ds.datacenter_id;


-- =============================================================================
-- NETWORKS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW core.vw_networks AS
SELECT
    n.id                        AS network_id,
    n.network_name,
    n.vlan_id,
    n.virtual_switch,
    n.cidr,
    n.gateway,
    n.dns_servers,
    n.platform_ref              AS network_platform_ref,
    n.metadata                  AS network_metadata,
    n.created_at                AS network_created_at,
    n.updated_at                AS network_updated_at,
    nt.name                     AS network_type,

    -- attached host count
    (
        SELECT count(*)
        FROM core.network_hosts nh
        WHERE nh.network_id = n.id
    )                           AS attached_host_count,

    -- attached vm count (via nics)
    (
        SELECT count(DISTINCT vn.vm_id)
        FROM core.vm_nics vn
        WHERE vn.network_id = n.id
    )                           AS attached_vm_count

FROM core.networks n
LEFT JOIN core.network_types      nt  ON nt.id  = n.network_type_id;