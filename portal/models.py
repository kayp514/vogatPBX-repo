#    DjangoPBX
#
#    MIT License
#
#    Copyright (c) 2016 - 2022 Adrian Fretwell <adrian@djangopbx.com>
#
#    Permission is hereby granted, free of charge, to any person obtaining a copy
#    of this software and associated documentation files (the "Software"), to deal
#    in the Software without restriction, including without limitation the rights
#    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#    copies of the Software, and to permit persons to whom the Software is
#    furnished to do so, subject to the following conditions:
#
#    The above copyright notice and this permission notice shall be included in all
#    copies or substantial portions of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#    SOFTWARE.
#
#    Contributor(s):
#    Adrian Fretwell <adrian@djangopbx.com>
#

from django.db import models
import uuid
from django.utils.translation import gettext_lazy as _

from pbx.commonchoices import (
    EnabledTrueFalseChoice, TargetCategoryChoice
)


class Menu(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name         = models.CharField(max_length=64, verbose_name=_('Name'))
    description  = models.CharField(max_length=128, blank=True, verbose_name=_('Description'))
    created      = models.DateTimeField(auto_now_add=True, blank=True, null=True, verbose_name=_('Created'))
    updated      = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name=_('Updated'))
    synchronised = models.DateTimeField(blank=True, null=True, verbose_name=_('Synchronised'))
    updated_by   = models.CharField(max_length=64, verbose_name=_('Updated by'))

    class Meta:
        db_table = 'pbx_menus'

    def uuid(self):
        return str(id)

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    menu_id      = models.ForeignKey('Menu', db_column='menu_id', on_delete=models.CASCADE, verbose_name=_('Menu'))
    parent_id    = models.ForeignKey('self', db_column='parent_id', on_delete=models.CASCADE, blank=True, null=True, verbose_name=_('Parent Menu Item'))
    title        = models.CharField(max_length=64, verbose_name=_('Title'))
    link         = models.CharField(max_length=128, blank=True, null=True, verbose_name=_('Link'))
    icon         = models.CharField(max_length=32, blank=True, null=True, verbose_name=_('Icon'))
    category     = models.CharField(max_length=16, choices=TargetCategoryChoice.choices, default=TargetCategoryChoice.CINTERNAL, verbose_name=_('Target'))
    protected    = models.CharField(max_length=8, choices=EnabledTrueFalseChoice.choices, default=EnabledTrueFalseChoice.CTRUE, verbose_name=_('Protected'))
    sequence     = models.DecimalField(max_digits=11, decimal_places=0,default=10, verbose_name=_('Order'))
    description  = models.CharField(max_length=128, blank=True, verbose_name=_('Description'))
    created      = models.DateTimeField(auto_now_add=True, blank=True, null=True, verbose_name=_('Created'))
    updated      = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name=_('Updated'))
    synchronised = models.DateTimeField(blank=True, null=True, verbose_name=_('Synchronised'))
    updated_by   = models.CharField(max_length=64, verbose_name=_('Updated by'))

    class Meta:
        db_table = 'pbx_menu_items'

    @property
    def id_str(self):
        return str(self.id)

    @property
    def parent_id_str(self):
        return str(self.parent_id.id)

    def __str__(self):
        return self.title


class MenuItemGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    menu_item_id = models.ForeignKey('MenuItem', db_column='menu_item_id', on_delete=models.CASCADE, verbose_name=_('Menu Item'))
    name         = models.CharField(max_length=64, blank=True, null=True)
    group_id     = models.ForeignKey('auth.Group', db_column='group_id', on_delete=models.CASCADE, verbose_name=_('Group'))
    created      = models.DateTimeField(auto_now_add=True, blank=True, null=True, verbose_name=_('Created'))
    updated      = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name=_('Updated'))
    synchronised = models.DateTimeField(blank=True, null=True, verbose_name=_('Synchronised'))
    updated_by   = models.CharField(max_length=64, verbose_name=_('Updated by'))

    class Meta:
        db_table = 'pbx_menu_item_groups'

    def save(self, *args, **kwargs):
        self.name = self.group_id.name
        super(MenuItemGroup, self).save(*args, **kwargs)

    def __str__(self):
        return str(self.group_id)

