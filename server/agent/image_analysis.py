"""Image description service. Image retention and speech stay with the host."""
import models
from service_mcp import call_service


class ImageAnalysis:
    def __init__(self, instructions, resolve, client):
        self.instructions, self.resolve, self.client = instructions, resolve, client

    async def describe(self, image_ref, *, timeout=20, max_chars=240):
        if models.LOCAL_TEST:
            return {'status': 'unavailable', 'reason': 'local_backend'}

        async def execute(arguments):
            image = self.resolve(arguments['image_ref'])
            if image is None:
                return {'status': 'not_retained'}
            model = models.model('eyes')
            response = await models.client_for('eyes', self.client()).chat.completions.create(**models.options(
                'eyes', model=model, timeout=timeout,
                messages=[{'role': 'system', 'content': self.instructions},
                          {'role': 'user', 'content': [{'type': 'image_url',
                             'image_url': {'url': image, 'detail': 'low'}}]}]))
            models.record('eyes', model, getattr(response, 'usage', None))
            text = ' '.join((response.choices[0].message.content or '').split())
            return {'status': 'completed' if text else 'empty', 'caption': text[:max_chars]}

        schema = {'type': 'object', 'properties': {'image_ref': {'type': 'string', 'maxLength': 80}},
                  'required': ['image_ref'], 'additionalProperties': False}
        return await call_service('vision', 'describe_image', execute, schema=schema,
                                  arguments={'image_ref': str(image_ref)}, timeout=timeout)
