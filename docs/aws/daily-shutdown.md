# Daily shutdown checklist

Run at the end of every working day

## Stop

1. **RDS** - the most expensive thing this project leaves running.

       aws rds stop-db-instance --db-instance-identifier dosimeter-db --region us-east-1

   Check it:

       aws rds describe-db-instances --db-instance-identifier dosimeter-db --region us-east-1 --query "DBInstances[0].DBInstanceStatus"

   Expect `stopping`, then `stopped`. AWS restarts a stopped instance after
   seven days on its own, so this is a daily job

2. **Local Docker**, if you were running the compose database:

       docker compose stop

## Start again in the morning

    aws rds start-db-instance --db-instance-identifier dosimeter-db --region us-east-1

It takes a few minutes to become `available`.

## Notes

- Stopping RDS keeps the storage, so the schema and seed rows survive. Note that this still has a small cost apparently. 
