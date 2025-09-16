from django.db import models



class Product(models.Model):
    name = models.CharField(max_length=255)
    parent = models.ForeignKey("self", models.DO_NOTHING, related_name='sub_products', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

