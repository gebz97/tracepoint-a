-- =============================================================================
-- SEED LOOKUPS
-- =============================================================================
INSERT INTO
    hypervisor_types (name)
VALUES
    ('esxi'),
    ('kvm'),
    ('hyper-v'),
    ('xen'),
    ('proxmox'),
    ('nutanix'),
    ('ovirt');

INSERT INTO
    platform_vendors (name)
VALUES
    ('vmware'),
    ('microsoft'),
    ('proxmox'),
    ('nutanix'),
    ('redhat'),
    ('canonical');

INSERT INTO
    datastore_types (name)
VALUES
    ('nfs'),
    ('iscsi'),
    ('fc'),
    ('local'),
    ('vsan'),
    ('ceph'),
    ('smb'),
    ('gluster'),
    ('rbd'),
    ('nvme-of');

INSERT INTO
    network_types (name)
VALUES
    ('standard'),
    ('distributed'),
    ('openvswitch'),
    ('linux_bridge'),
    ('sriov'),
    ('overlay');

INSERT INTO
    disk_formats (name)
VALUES
    ('thin'),
    ('thick_lazy'),
    ('thick_eager'),
    ('qcow2'),
    ('raw'),
    ('vmdk'),
    ('vhd'),
    ('vhdx');

INSERT INTO
    adapter_types (name)
VALUES
    ('vmxnet3'),
    ('e1000e'),
    ('virtio'),
    ('rtl8139'),
    ('hyperv-net'),
    ('xe'),
    ('sriov');

INSERT INTO
    cluster_types (name)
VALUES
    ('compute'),
    ('storage'),
    ('hyper-converged'),
    ('management');

INSERT INTO
    cpu_archs (name)
VALUES
    ('x86_64'),
    ('aarch64'),
    ('i386'),
    ('ppc64'),
    ('s390x');

INSERT INTO
    power_states (name)
VALUES
    ('running'),
    ('stopped'),
    ('suspended'),
    ('paused'),
    ('unknown');

INSERT INTO
    host_statuses (name)
VALUES
    ('online'),
    ('offline'),
    ('maintenance'),
    ('unknown');

INSERT INTO
    environments (name, abbr)
VALUES
    ('poc', 'c'),
    ('dev', 'v'),
    ('sit', 't'),
    ('uat', 'u'),
    ('pre', 'e'),
    ('prd', 'p'),
    ('dr', 'd');