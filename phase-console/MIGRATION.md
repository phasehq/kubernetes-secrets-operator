# Database Migration Guide

This document provides instructions for handling database migrations safely when using the Phase Console Helm chart.

## Pre-Migration Checklist
Before installing or upgrading the chart (which triggers the migration Job):

1.  **Backup Verification**: Ensure you have a recent, verified backup of your PostgreSQL database.
    ```bash
    # Example backup command (adjust for your environment)
    pg_dump -h <db-host> -U <db-user> -d <db-name> > backup_$(date +%F).sql
    ```
2.  **Snapshot**: If running on a cloud provider (AWS RDS, GKE, etc.), take a snapshot of the volume.

## Migration Process
The migration runs automatically via the `job-migrations.yaml` hook during `helm install` or `helm upgrade`.

- **Success**: The Job completes, and the new pods start.
- **Failure**: The Job will retry (`backoffLimit: 6`). If it eventually fails, the deployment will pause.

## Rollback Instructions (Manual)
Kubernetes Jobs do not automatically roll back database schema changes. If a migration fails mid-stream:

1.  **Identify Failure**: Check the logs of the migration job.
    ```bash
    kubectl logs -l job-name=<release-name>-migrations
    ```
2.  **Restore Backup**:
    If the database schema is in a corrupted state, you MUST restore from the backup taken before the migration.
    *Running "down" migrations manually is risky and not supported by the automated Job.*

    ```bash
    # Stop the application
    kubectl scale deployment <release-name>-backend --replicas=0
    
    # Restore DB
    psql -h <db-host> -U <db-user> -d <db-name> < backup_previous.sql
    
    # Restore previous Chart version
    helm rollback <release-name> <previous-revision>
    ```

3.  **Transaction Safety**:
    Postgres DDL transactions are supported. The migration script attempts to run atomically where possible. However, explicit backups are the only 100% safe rollback method.
