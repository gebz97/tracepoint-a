-- =============================================================================
-- INDEXES
-- =============================================================================
CREATE INDEX idx_clusters_datacenter ON clusters USING btree (datacenter_id);

CREATE INDEX idx_clusters_type ON clusters USING btree (cluster_type_id);

CREATE INDEX idx_hosts_cluster ON hypervisor_hosts USING btree (cluster_id);

CREATE INDEX idx_hosts_status ON hypervisor_hosts USING btree (status_id);

CREATE INDEX idx_hosts_type ON hypervisor_hosts USING btree (hypervisor_type_id);

CREATE INDEX idx_hosts_vendor ON hypervisor_hosts USING btree (platform_vendor_id);

CREATE INDEX idx_hosts_metadata ON hypervisor_hosts USING gin (metadata);

CREATE INDEX idx_datastores_datacenter ON datastores USING btree (datacenter_id);

CREATE INDEX idx_datastores_type ON datastores USING btree (datastore_type_id);

CREATE INDEX idx_networks_type ON networks USING btree (network_type_id);

CREATE INDEX idx_compute_pools_cluster ON compute_pools USING btree (cluster_id);

CREATE INDEX idx_compute_pools_parent ON compute_pools USING btree (parent_id);

CREATE INDEX idx_vms_host ON vms USING btree (hypervisor_host_id);

CREATE INDEX idx_vms_pool ON vms USING btree (compute_pool_id);

CREATE INDEX idx_vms_power_state ON vms USING btree (power_state_id);

CREATE INDEX idx_vms_environment ON vms USING btree (environment_id);

CREATE INDEX idx_vms_metadata ON vms USING gin (metadata);

CREATE INDEX idx_vm_disks_vm ON vm_disks USING btree (vm_id);

CREATE INDEX idx_vm_disks_datastore ON vm_disks USING btree (datastore_id);

CREATE INDEX idx_vm_disks_format ON vm_disks USING btree (disk_format_id);

CREATE INDEX idx_vm_nics_vm ON vm_nics USING btree (vm_id);

CREATE INDEX idx_vm_nics_network ON vm_nics USING btree (network_id);

CREATE INDEX idx_snapshots_vm ON vm_snapshots USING btree (vm_id);

CREATE INDEX idx_snapshots_parent ON vm_snapshots USING btree (parent_id);