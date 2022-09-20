import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info(f"Event: {event}")

    # Mark users as confirmed to allow logins without email verification
    # This assumes email validation is done at the application level
    event['response'] = {
        'autoConfirmUser': True,
        'autoVerifyEmail': False,
        'autoVerifyPhone': False,
    }

    logger.info(f"Response: {event['response']}")
    return event
