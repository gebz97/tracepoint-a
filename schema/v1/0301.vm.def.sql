-- =============================================================================
-- VM TABLES
-- =============================================================================

CREATE TABLE core.vms (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hypervisor_host_id  int             NULL REFERENCES core.hypervisor_hosts(id),
    compute_pool_id     int             NULL REFERENCES core.compute_pools(id),
    template_id         int             NULL REFERENCES core.templates(id),
    power_state_id      int             NULL REFERENCES core.power_states(id),
    arch_id             int             NULL REFERENCES core.cpu_archs(id),
    environment_id      int             NULL REFERENCES core.environments(id),
    service_id          int             NULL REFERENCES core.services(id),
    team_id             int             NULL REFERENCES core.teams(id),
    project_id          int             NULL REFERENCES core.projects(id),
    cost_center_id      int             NULL REFERENCES core.cost_centers(id),
    vm_name             varchar(255)    NOT NULL UNIQUE,
    ipv4                varchar(55)     NOT NULL UNIQUE,
    service             varchar(55)     NULL,
    os_type_id          int             NULL REFERENCES core.os_types(id),
    platform_ref        varchar(255)    NULL,
    cpus                int             NULL,
    memory_mb           int8            NULL,
    storage_total_gb    int8            NULL,
    metadata            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE core.vm_disks (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id               int             NOT NULL REFERENCES core.vms(id),
    datastore_id        int             NOT NULL REFERENCES core.datastores(id),
    disk_format_id      int             NULL     REFERENCES core.disk_formats(id),
    label               varchar(55)     NULL,
    size_gb             int8            NOT NULL,
    disk_path           varchar(512)    NULL,
    boot_disk           bool            NOT NULL DEFAULT false,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE core.vm_nics (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id               int             NOT NULL REFERENCES core.vms(id),
    network_id          int             NOT NULL REFERENCES core.networks(id),
    adapter_type_id     int             NULL     REFERENCES core.adapter_types(id),
    mac_address         varchar(55)     NULL,
    ipv4                varchar(55)     NULL,
    ipv6                varchar(55)     NULL,
    connected           bool            NOT NULL DEFAULT true,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE core.vm_snapshots (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id               int             NOT NULL REFERENCES core.vms(id),
    parent_id           int             NULL     REFERENCES core.vm_snapshots(id),
    snapshot_name       varchar(255)    NOT NULL,
    description         text            NULL,
    size_gb             int8            NULL,
    quiesced            bool            NOT NULL DEFAULT false,
    platform_ref        varchar(255)    NULL,
    created_at          timestamp       NOT NULL DEFAULT now()
);
