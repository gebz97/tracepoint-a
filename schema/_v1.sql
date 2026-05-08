-- =============================================================================
-- LOOKUP TABLES
-- =============================================================================

CREATE TABLE public.hypervisor_types (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

CREATE TABLE public.platform_vendors (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

CREATE TABLE public.datastore_types (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

CREATE TABLE public.network_types (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

CREATE TABLE public.disk_formats (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

CREATE TABLE public.adapter_types (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

CREATE TABLE public.cluster_types (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

CREATE TABLE public.cpu_archs (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

CREATE TABLE public.power_states (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

CREATE TABLE public.host_statuses (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

CREATE TABLE public.environments (
    id      int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    varchar(55) NOT NULL UNIQUE
);

-- =============================================================================
-- SEED LOOKUPS
-- =============================================================================

INSERT INTO public.hypervisor_types (name) VALUES
    ('esxi'), ('kvm'), ('hyper-v'), ('xen'), ('proxmox'), ('nutanix'), ('ovirt');

INSERT INTO public.platform_vendors (name) VALUES
    ('vmware'), ('microsoft'), ('proxmox'), ('nutanix'), ('redhat'), ('canonical');

INSERT INTO public.datastore_types (name) VALUES
    ('nfs'), ('iscsi'), ('fc'), ('local'), ('vsan'), ('ceph'), ('smb'), ('gluster'), ('rbd'), ('nvme-of');

INSERT INTO public.network_types (name) VALUES
    ('standard'), ('distributed'), ('openvswitch'), ('linux_bridge'), ('sriov'), ('overlay');

INSERT INTO public.disk_formats (name) VALUES
    ('thin'), ('thick_lazy'), ('thick_eager'), ('qcow2'), ('raw'), ('vmdk'), ('vhd'), ('vhdx');

INSERT INTO public.adapter_types (name) VALUES
    ('vmxnet3'), ('e1000e'), ('virtio'), ('rtl8139'), ('hyperv-net'), ('xe'), ('sriov');

INSERT INTO public.cluster_types (name) VALUES
    ('compute'), ('storage'), ('hyper-converged'), ('management');

INSERT INTO public.cpu_archs (name) VALUES
    ('x86_64'), ('aarch64'), ('i386'), ('ppc64'), ('s390x');

INSERT INTO public.power_states (name) VALUES
    ('running'), ('stopped'), ('suspended'), ('paused'), ('unknown');

INSERT INTO public.host_statuses (name) VALUES
    ('online'), ('offline'), ('maintenance'), ('unknown');

INSERT INTO public.environments (name) VALUES
    ('dev'),
    ('sit'),
    ('uat'),
    ('pre'),
    ('prd'),
    ('dr');

-- =============================================================================
-- ORGANIZATIONAL
-- =============================================================================

CREATE TABLE public.teams (
    id              int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_name       varchar(255)    NOT NULL UNIQUE,
    description     text            NULL,
    email           varchar(255)    NULL,       -- team distribution list
    metadata        jsonb           NULL,
    created_at      timestamp       NOT NULL DEFAULT now(),
    updated_at      timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE public.contacts (
    id              int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name       varchar(255)    NOT NULL,
    email           varchar(255)    NOT NULL UNIQUE,
    metadata        jsonb           NULL,
    created_at      timestamp       NOT NULL DEFAULT now(),
    updated_at      timestamp       NOT NULL DEFAULT now()
);

-- team members (many-to-many, a contact can be in multiple teams)
CREATE TABLE public.team_contacts (
    team_id         int             NOT NULL REFERENCES public.teams(id),
    contact_id      int             NOT NULL REFERENCES public.contacts(id),
    role            varchar(55)     NULL,       -- 'lead', 'member', 'on-call' ...
    PRIMARY KEY (team_id, contact_id)
);

CREATE TABLE public.services (
    id              int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_id         int             NOT NULL REFERENCES public.teams(id),
    service_name    varchar(255)    NOT NULL UNIQUE,
    description     text            NULL,
    metadata        jsonb           NULL,
    created_at      timestamp       NOT NULL DEFAULT now(),
    updated_at      timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE public.cost_centers (
    id              int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cost_center_code    varchar(55)     NOT NULL UNIQUE,    -- e.g. 'CC-1042'
    cost_center_name    varchar(255)    NOT NULL,
    description         text            NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE public.projects (
    id              int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_id         int             NOT NULL REFERENCES public.teams(id),
    cost_center_id  int             NULL REFERENCES public.cost_centers(id),
    project_name    varchar(255)    NOT NULL UNIQUE,
    description     text            NULL,
    start_date      date            NULL,
    end_date        date            NULL,
    metadata        jsonb           NULL,
    created_at      timestamp       NOT NULL DEFAULT now(),
    updated_at      timestamp       NOT NULL DEFAULT now()
);

-- =============================================================================
-- CORE TABLES
-- =============================================================================

CREATE TABLE public.datacenters (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datacenter_name     varchar(255)    NOT NULL UNIQUE,
    location            varchar(255)    NULL,
    description         text            NULL,
    metadata            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE public.clusters (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datacenter_id       int             NOT NULL REFERENCES public.datacenters(id),
    cluster_type_id     int             NULL     REFERENCES public.cluster_types(id),
    cluster_name        varchar(255)    NOT NULL,
    high_availability   bool            NOT NULL DEFAULT false,
    load_balancing      bool            NOT NULL DEFAULT false,
    description         text            NULL,
    features            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now(),
    CONSTRAINT clusters_unique UNIQUE (datacenter_id, cluster_name)
);

CREATE TABLE public.hypervisor_hosts (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id          int             NOT NULL REFERENCES public.clusters(id),
    hypervisor_type_id  int             NOT NULL REFERENCES public.hypervisor_types(id),
    platform_vendor_id  int             NULL     REFERENCES public.platform_vendors(id),
    status_id           int             NOT NULL REFERENCES public.host_statuses(id),
    hostname            varchar(255)    NOT NULL UNIQUE,
    ipv4                varchar(55)     NOT NULL UNIQUE,
    ipmi_ip             varchar(55)     NULL,
    hypervisor_version  varchar(55)     NULL,
    platform_ref        varchar(255)    NULL,
    manufacturer        varchar(255)    NULL,
    model               varchar(255)    NULL,
    serial_number       varchar(255)    NULL,
    cpu_model           varchar(255)    NULL,
    cpu_sockets         int             NULL,
    cpu_cores           int             NULL,
    memory_mb           int8            NULL,
    maintenance_mode    bool            NOT NULL DEFAULT false,
    metadata            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE public.datastores (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datacenter_id       int             NOT NULL REFERENCES public.datacenters(id),
    datastore_type_id   int             NOT NULL REFERENCES public.datastore_types(id),
    datastore_name      varchar(255)    NOT NULL UNIQUE,
    ds_path             varchar(512)    NULL,
    total_gb            int8            NULL,
    used_gb             int8            NULL,
    free_gb             int8            GENERATED ALWAYS AS (total_gb - used_gb) STORED,
    thin_provisioned    bool            NOT NULL DEFAULT true,
    replication_enabled bool            NOT NULL DEFAULT false,
    platform_ref        varchar(255)    NULL,
    metadata            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE public.datastore_hosts (
    datastore_id        int             NOT NULL REFERENCES public.datastores(id),
    host_id             int             NOT NULL REFERENCES public.hypervisor_hosts(id),
    mounted_at          timestamp       NOT NULL DEFAULT now(),
    read_only           bool            NOT NULL DEFAULT false,
    PRIMARY KEY (datastore_id, host_id)
);

CREATE TABLE public.networks (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_type_id     int             NULL     REFERENCES public.network_types(id),
    network_name        varchar(255)    NOT NULL,
    vlan_id             int             NULL,
    virtual_switch      varchar(255)    NULL,
    cidr                varchar(55)     NULL,
    gateway             varchar(55)     NULL,
    dns_servers         text[]          NULL,
    platform_ref        varchar(255)    NULL,
    metadata            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now(),
    CONSTRAINT networks_unique UNIQUE (network_name, vlan_id)
);

CREATE TABLE public.network_hosts (
    network_id          int             NOT NULL REFERENCES public.networks(id),
    host_id             int             NOT NULL REFERENCES public.hypervisor_hosts(id),
    PRIMARY KEY (network_id, host_id)
);

CREATE TABLE public.compute_pools (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id          int             NOT NULL REFERENCES public.clusters(id),
    parent_id           int             NULL     REFERENCES public.compute_pools(id),
    pool_name           varchar(255)    NOT NULL,
    cpu_shares          int             NULL,
    cpu_limit_mhz       int             NULL,
    mem_shares          int             NULL,
    mem_limit_mb        int8            NULL,
    platform_ref        varchar(255)    NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now(),
    CONSTRAINT compute_pools_unique UNIQUE (cluster_id, pool_name)
);

CREATE TABLE public.templates (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datastore_id        int             NULL REFERENCES public.datastores(id),
    arch_id             int             NULL REFERENCES public.cpu_archs(id),
    template_name       varchar(255)    NOT NULL UNIQUE,
    distribution        varchar(255)    NULL,
    os_version          varchar(255)    NULL,
    platform_ref        varchar(255)    NULL,
    notes               text            NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE public.vms (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hypervisor_host_id  int             NULL REFERENCES public.hypervisor_hosts(id),
    compute_pool_id     int             NULL REFERENCES public.compute_pools(id),
    template_id         int             NULL REFERENCES public.templates(id),
    power_state_id      int             REFERENCES public.power_states(id),
    arch_id             int             NULL REFERENCES public.cpu_archs(id),
    environment_id      int             NULL REFERENCES public.environments(id),
    service_id          int             NULL REFERENCES public.services(id),
    team_id             int             NULL REFERENCES public.teams(id),
    project_id          int             NULL REFERENCES public.projects(id),
    cost_center_id      int             NULL REFERENCES public.cost_centers(id),
    vm_name             varchar(255)    NOT NULL UNIQUE,
    ipv4                varchar(55)     NOT NULL UNIQUE,
    service             varchar(55)     NULL,
    distribution        varchar(255)    NULL,
    os_version          varchar(255)    NULL,
    os_major            int             NULL,
    platform_ref        varchar(255)    NULL,
    cpus                int             NULL,
    memory_mb           int8            NULL,
    storage_total_gb    int8            NULL,
    metadata            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE public.vm_disks (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id               int             NOT NULL REFERENCES public.vms(id),
    datastore_id        int             NOT NULL REFERENCES public.datastores(id),
    disk_format_id      int             NULL     REFERENCES public.disk_formats(id),
    label               varchar(55)     NULL,
    size_gb             int8            NOT NULL,
    disk_path           varchar(512)    NULL,
    boot_disk           bool            NOT NULL DEFAULT false,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE public.vm_nics (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id               int             NOT NULL REFERENCES public.vms(id),
    network_id          int             NOT NULL REFERENCES public.networks(id),
    adapter_type_id     int             NULL     REFERENCES public.adapter_types(id),
    mac_address         varchar(55)     NULL,
    ipv4                varchar(55)     NULL,
    ipv6                varchar(55)     NULL,
    connected           bool            NOT NULL DEFAULT true,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE public.vm_snapshots (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id               int             NOT NULL REFERENCES public.vms(id),
    parent_id           int             NULL     REFERENCES public.vm_snapshots(id),
    snapshot_name       varchar(255)    NOT NULL,
    description         text            NULL,
    size_gb             int8            NULL,
    quiesced            bool            NOT NULL DEFAULT false,
    platform_ref        varchar(255)    NULL,
    created_at          timestamp       NOT NULL DEFAULT now()
);

-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX idx_clusters_datacenter        ON public.clusters          USING btree (datacenter_id);
CREATE INDEX idx_clusters_type              ON public.clusters          USING btree (cluster_type_id);

CREATE INDEX idx_hosts_cluster              ON public.hypervisor_hosts  USING btree (cluster_id);
CREATE INDEX idx_hosts_status               ON public.hypervisor_hosts  USING btree (status_id);
CREATE INDEX idx_hosts_type                 ON public.hypervisor_hosts  USING btree (hypervisor_type_id);
CREATE INDEX idx_hosts_vendor               ON public.hypervisor_hosts  USING btree (platform_vendor_id);
CREATE INDEX idx_hosts_metadata             ON public.hypervisor_hosts  USING gin   (metadata);

CREATE INDEX idx_datastores_datacenter      ON public.datastores        USING btree (datacenter_id);
CREATE INDEX idx_datastores_type            ON public.datastores        USING btree (datastore_type_id);

CREATE INDEX idx_networks_type              ON public.networks          USING btree (network_type_id);

CREATE INDEX idx_compute_pools_cluster      ON public.compute_pools     USING btree (cluster_id);
CREATE INDEX idx_compute_pools_parent       ON public.compute_pools     USING btree (parent_id);

CREATE INDEX idx_vms_host                   ON public.vms               USING btree (hypervisor_host_id);
CREATE INDEX idx_vms_pool                   ON public.vms               USING btree (compute_pool_id);
CREATE INDEX idx_vms_power_state            ON public.vms               USING btree (power_state_id);
CREATE INDEX idx_vms_environment            ON public.vms               USING btree (environment_id);
CREATE INDEX idx_vms_metadata               ON public.vms               USING gin   (metadata);

CREATE INDEX idx_vm_disks_vm                ON public.vm_disks          USING btree (vm_id);
CREATE INDEX idx_vm_disks_datastore         ON public.vm_disks          USING btree (datastore_id);
CREATE INDEX idx_vm_disks_format            ON public.vm_disks          USING btree (disk_format_id);

CREATE INDEX idx_vm_nics_vm                 ON public.vm_nics           USING btree (vm_id);
CREATE INDEX idx_vm_nics_network            ON public.vm_nics           USING btree (network_id);

CREATE INDEX idx_snapshots_vm               ON public.vm_snapshots      USING btree (vm_id);
CREATE INDEX idx_snapshots_parent           ON public.vm_snapshots      USING btree (parent_id);

-- =============================================================================
-- FULL VM VIEW
-- =============================================================================

CREATE OR REPLACE VIEW public.vw_vms AS
SELECT
    -- vm core
    v.id                        AS vm_id,
    v.vm_name,
    v.ipv4,
    v.service                   AS vm_service_tag,      -- legacy free-text field
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

FROM public.vms v
LEFT JOIN public.power_states       ps  ON ps.id   = v.power_state_id
LEFT JOIN public.environments       e   ON e.id    = v.environment_id
LEFT JOIN public.cpu_archs          a   ON a.id    = v.arch_id
LEFT JOIN public.services           svc ON svc.id  = v.service_id
LEFT JOIN public.teams              tm  ON tm.id   = v.team_id
LEFT JOIN public.teams              stm ON stm.id  = svc.team_id
LEFT JOIN public.projects           pr  ON pr.id   = v.project_id
LEFT JOIN public.cost_centers       cc  ON cc.id   = v.cost_center_id
LEFT JOIN public.hypervisor_hosts   hh  ON hh.id   = v.hypervisor_host_id
LEFT JOIN public.hypervisor_types   ht  ON ht.id   = hh.hypervisor_type_id
LEFT JOIN public.platform_vendors   pv  ON pv.id   = hh.platform_vendor_id
LEFT JOIN public.host_statuses      hs  ON hs.id   = hh.status_id
LEFT JOIN public.clusters           cl  ON cl.id   = hh.cluster_id
LEFT JOIN public.cluster_types      clt ON clt.id  = cl.cluster_type_id
LEFT JOIN public.datacenters        dc  ON dc.id   = cl.datacenter_id
LEFT JOIN public.compute_pools      cp  ON cp.id   = v.compute_pool_id
LEFT JOIN public.templates          t   ON t.id    = v.template_id;


-- =============================================================================
-- VM DISKS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW public.vw_vm_disks AS
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

FROM public.vm_disks vd
LEFT JOIN public.disk_formats       df  ON df.id  = vd.disk_format_id
LEFT JOIN public.vms                v   ON v.id   = vd.vm_id
LEFT JOIN public.power_states       ps  ON ps.id  = v.power_state_id
LEFT JOIN public.environments       e   ON e.id   = v.environment_id
LEFT JOIN public.datastores         ds  ON ds.id  = vd.datastore_id
LEFT JOIN public.datastore_types    dst ON dst.id = ds.datastore_type_id
LEFT JOIN public.datacenters        dc  ON dc.id  = ds.datacenter_id;


-- =============================================================================
-- VM NICS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW public.vw_vm_nics AS
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

FROM public.vm_nics vn
LEFT JOIN public.adapter_types      at  ON at.id  = vn.adapter_type_id
LEFT JOIN public.vms                v   ON v.id   = vn.vm_id
LEFT JOIN public.power_states       ps  ON ps.id  = v.power_state_id
LEFT JOIN public.environments       e   ON e.id   = v.environment_id
LEFT JOIN public.networks           n   ON n.id   = vn.network_id
LEFT JOIN public.network_types      nt  ON nt.id  = n.network_type_id;


-- =============================================================================
-- VM SNAPSHOTS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW public.vw_vm_snapshots AS
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

FROM public.vm_snapshots s
LEFT JOIN public.vm_snapshots       sp  ON sp.id  = s.parent_id
LEFT JOIN public.vms                v   ON v.id   = s.vm_id
LEFT JOIN public.power_states       ps  ON ps.id  = v.power_state_id
LEFT JOIN public.environments       e   ON e.id   = v.environment_id;


-- =============================================================================
-- HYPERVISOR HOSTS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW public.vw_hypervisor_hosts AS
SELECT
    hh.id                       AS host_id,
    hh.hostname,
    hh.ipv4,
    hh.ipmi_ip,
    hh.hypervisor_version,
    hh.platform_ref             AS host_platform_ref,
    hh.manufacturer,
    hh.model,
    hh.serial_number,
    hh.cpu_model,
    hh.cpu_sockets,
    hh.cpu_cores,
    hh.cpu_sockets * hh.cpu_cores
                                AS total_cores,
    hh.memory_mb,
    hh.maintenance_mode,
    hh.metadata                 AS host_metadata,
    hh.created_at               AS host_created_at,
    hh.updated_at               AS host_updated_at,
    ht.name                     AS hypervisor_type,
    pv.name                     AS platform_vendor,
    hs.name                     AS host_status,

    -- cluster
    cl.id                       AS cluster_id,
    cl.cluster_name,
    cl.high_availability        AS cluster_ha,
    cl.load_balancing           AS cluster_lb,
    ct.name                     AS cluster_type,

    -- datacenter
    dc.id                       AS datacenter_id,
    dc.datacenter_name,
    dc.location                 AS datacenter_location,

    -- vm counts
    (
        SELECT count(*)
        FROM public.vms v
        WHERE v.hypervisor_host_id = hh.id
    )                           AS vm_count,
    (
        SELECT count(*)
        FROM public.vms v
        JOIN public.power_states ps ON ps.id = v.power_state_id
        WHERE v.hypervisor_host_id = hh.id
        AND ps.name = 'running'
    )                           AS running_vm_count

FROM public.hypervisor_hosts hh
LEFT JOIN public.hypervisor_types   ht  ON ht.id  = hh.hypervisor_type_id
LEFT JOIN public.platform_vendors   pv  ON pv.id  = hh.platform_vendor_id
LEFT JOIN public.host_statuses      hs  ON hs.id  = hh.status_id
LEFT JOIN public.clusters           cl  ON cl.id  = hh.cluster_id
LEFT JOIN public.cluster_types      ct  ON ct.id  = cl.cluster_type_id
LEFT JOIN public.datacenters        dc  ON dc.id  = cl.datacenter_id;


-- =============================================================================
-- DATASTORES VIEW
-- =============================================================================

CREATE OR REPLACE VIEW public.vw_datastores AS
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
        FROM public.datastore_hosts dh
        WHERE dh.datastore_id = ds.id
    )                           AS mounted_host_count

FROM public.datastores ds
LEFT JOIN public.datastore_types    dst ON dst.id = ds.datastore_type_id
LEFT JOIN public.datacenters        dc  ON dc.id  = ds.datacenter_id;


-- =============================================================================
-- NETWORKS VIEW
-- =============================================================================

CREATE OR REPLACE VIEW public.vw_networks AS
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
        FROM public.network_hosts nh
        WHERE nh.network_id = n.id
    )                           AS attached_host_count,

    -- attached vm count (via nics)
    (
        SELECT count(DISTINCT vn.vm_id)
        FROM public.vm_nics vn
        WHERE vn.network_id = n.id
    )                           AS attached_vm_count

FROM public.networks n
LEFT JOIN public.network_types      nt  ON nt.id  = n.network_type_id;
