
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


