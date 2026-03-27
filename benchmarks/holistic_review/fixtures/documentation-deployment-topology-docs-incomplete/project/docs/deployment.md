# Worker Deployment Guide

The sync worker is stateless, so you can run multiple replicas behind the scheduler without any shared coordination layer.

Recommended production topology:

1. Start one scheduler instance.
2. Scale `sync-worker` to 3 replicas.
3. Let each worker claim jobs independently because lease state is not stored locally.