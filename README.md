# Auth0 to Cognito

## 0. Introduction

The purpose of this repository is to compile resources and code necessary to migrate an application from using Auth0 as an authentication provider to using Cognito with little to no impact on users. This migration is only complicated by applications utilizing Auth0's username and password database as a connection. This requires some mechanism by which we can move that database to Cognito and avoid having all users reset passwords. Unfortunately, Auth0 does not make getting that database easy or potentially even possible with passwords intact.

## 1. Plan

As outlined [here](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-import-using-lambda.html), Cognito makes it possible to seamlessly migrate users one-by-one utilizing triggers. In this instance, whenever a valid user in Auth0 tries to sign into their application after it has been switched to Cognito, their username and password will naturally fail. What Cognito does is allows us to hook into that event, and see if that user existed in our prior authentication provider, and if so, move them to Cognito, and also authenticate their Cognito login normally. The user will be created in Cognito, with their existing Auth0 password, and they won't notice any difference. This trigger also handles instances of password resets where the entered email does not exist in Cognito. We can check Auth0 to see if they have an existing account, and if so, add them to Cognito, and let Cognito process the password reset. These two events allow us to gradually move users away from Auth0 without requiring anything of them other than to just login normally.

## 2. Implementation

The trigger script in this repository handles both events as described above, failed login and password reset. The failed login event, when passed to the trigger script, will include both the username and password that were attempted for the failed Cognito login. We take those values and use Auth0's Authentication API to attempt to login the user there. If that login succeeds, we have proven the user's credentials are in fact valid and we tell Cognito to confirm that user and allow them to login. Similarly for password resets, we use the Auth0 Management API to query all users for the entered email address. If we find a user with the matching email in Auth0, we tell Cognito to create that user in its own database, we mark their email as verified, and Cognito proceeds with the password reset.

## 3. Usage

### a. Auth0 Setup ###

To get started, we first need a set of client credentials for the application in Auth0 we are migrating from. In addition, we need to grant this application a single permission on Auth0's Management API.

1. Log into the Auth0 dashboard
2. Select 'Applications' from the side menu
3. Select 'APIs' from the submenu
4. Select the 'Auth0 Management API'
5. Select 'Machine to Machine Applications'
6. Find your application and toggle the 'Authorize' button
7. Expand your application's entry by clicking the chevron next to the 'Authorize' toggle
8. Select the 'read:users' permission in the 'Permissions' box and click 'Update'

You can verify your application is correctly setup by requesting an access token from the Auth0 Management API and checking the returned scope for the token.

```
curl --request POST --url https://hms-dbmi.auth0.com/oauth/token --header 'content-type: application/json' --data '{"client_id":"YOUR_CLIENT_ID","client_secret":"YOUR_CLIENT_SECRET","audience":"https://hms-dbmi.auth0.com/api/v2/","grant_type":"client_credentials"}'
```

The response should include an access token as well as scope set to 'read:users'

```
{"access_token":"eyJh...","scope":"read:users","expires_in":2592000,"token_type":"Bearer"}
```
### b. CloudFormation

Create a stack using the included CloudFormation template to create the resources for the Cognito trigger. This stack creates the Lambda function, the IAM role for the function as well as the invocation permission that allows Cognito to execute the function as needed. Also created is a secret to store your previously prepared Auth0 application client ID and client secret.


### c. Cognito

Once the stack is created we still have a few remaining tasks:

1. Build the Lambda function's source using the `build.sh` script in this repository. Once run, a file `user-migration-trigger.zip` will be created. Upload that as the Lambda's source using the AWS Console.
2. Add your applications credentials to the created secret in Secrets Manager. An object was created with placeholders for the necessary values but the plaintext object should look like:
```
{
    "domain":"hms-dbmi.auth0.com",
    "client_id":"YOUR_CLIENT_ID",
    "client_secret":"YOUR_CLIENT_SECRET"
}
```
3. We now need to add the created Lambda function as the trigger for the Cognito User Pool.
    1. Select your User Pool in the AWS Cognito console
    2. Select 'User Pool Properties'
    3. Select 'Add Lambda Trigger'
    4. Select the 'Sign-up' trigger type
    5. Select the 'Migrate user trigger' option
    6. Select the create Lambda function in the 'Assign Lambda function' box
