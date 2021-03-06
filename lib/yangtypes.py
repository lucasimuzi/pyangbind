"""
Copyright 2015, Rob Shakir, BT plc. (rob.shakir@bt.com, rjs@rob.sh)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import numpy as np
from decimal import Decimal
import uuid
import re
import collections

NUMPY_INTEGER_TYPES = [np.uint8, np.uint16, np.uint32, np.uint64,
                    np.int8, np.int16, np.int32, np.int64]

def RestrictedPrecisionDecimalType(*args, **kwargs):
  """
    Function to return a new type that is based on decimal.Decimal with
    an arbitrary restricted precision.
  """
  precision = kwargs.pop("precision", False)
  class RestrictedPrecisionDecimal(Decimal):
    """
      Class extending decimal.Decimal to restrict the precision that is
      stored, supporting the fraction-digits argument of the YANG decimal64
      type.
    """
    _precision = 10.0**(-1.0*int(precision))
    def __new__(self, *args, **kwargs):
      """
        Overloads the decimal __new__ function in order to round the input
        value to the new value.
      """
      if not self._precision is None:
        if len(args):
          value = Decimal(args[0]).quantize(Decimal(str(self._precision)))
        else:
          value = Decimal(0)
      elif len(args):
        value = Decimal(args[0])
      else:
        value = Decimal(0)
      obj = Decimal.__new__(self, value, **kwargs)
      return obj
  return type(RestrictedPrecisionDecimal(*args, **kwargs))

def RestrictedClassType(*args, **kwargs):
  """
    Function to return a new type that restricts an arbitrary base_type with
    a specified restriction. The restriction_type specified determines the
    type of restriction placed on the class, and the restriction_arg gives
    any input data that this function needs.
  """
  base_type = kwargs.pop("base_type", str)
  restriction_type = kwargs.pop("restriction_type", None)
  restriction_arg = kwargs.pop("restriction_arg", None)

  class RestrictedClass(base_type):
    """
      A class that restricts the base_type class with a new function that the
      input value is validated against before being applied. The function is
      a static method which is assigned to _restricted_test.
    """
    _restriction_type = restriction_type
    _restriction_arg = restriction_arg
    _restriction_test = None

    def __init__(self, *args, **kwargs):
      """
        Overloads the base_class __init__ method to check the input argument
        against the validation function - returns on instance of the base_type
        class, which can be manipulated as per a usual Python object.
      """
      try:
        self.__check(args[0])
      except IndexError:
        pass
      super(RestrictedClass, self).__init__(*args, **kwargs)

    def __new__(self, *args, **kwargs):
      """
        Create a new class instance, and dynamically define the
        _restriction_test method so that it can be called by other functions.
      """
      def convert_regexp(pattern):
        if not pattern[0] == "^":
          pattern = "^%s" % pattern
        if not pattern[len(pattern)-1] == "$":
          pattern = "%s$" % pattern
        return pattern

      val = False
      try:
        val = args[0]
      except IndexError:
        pass
      if restriction_type == "pattern":
        tests = []
        if isinstance(restriction_arg, list):
          for pattern in restriction_arg:
            tests.append(re.compile(convert_regexp(pattern)).match)
        else:
          tests.append(re.compile(convert_regexp(restriction_arg)).match)
        self._tests = tests
        self._restriction_test = staticmethod(lambda val: False if False in [True if t(val) else False for t in tests] else True)
        self._restriction_arg = [i + "$" for i in restriction_arg] if isinstance(restriction_arg,list) else [restriction_arg+"$"]
        self._restriction_type = restriction_type
      elif restriction_type == "range":
        x = [base_type(i) for i in \
          re.sub("(?P<low>[0-9]+)([ ]+)?\.\.([ ]+)?(?P<high>[0-9]+)", \
            "\g<low>,\g<high>", restriction_arg).split(",")]
        self._restriction_test = staticmethod(lambda i: i >= x[0] and i <= x[1])
        self._restriction_arg = restriction_arg
        self._restriction_type = restriction_type
        try:
          val = int(val)
        except:
          raise TypeError, "must specify a numeric type for a range argument"
      elif restriction_type == "dict_key":
        # populate enum values
        used_values = []
        for k in restriction_arg:
          if "value" in restriction_arg[k]:
            used_values.append(int(restriction_arg[k]["value"]))
        c = 0
        for k in restriction_arg:
          while c in used_values:
            c += 1
          if not "value" in restriction_arg[k]:
            restriction_arg[k]["value"] = c
          c += 1
        self._restriction_test = staticmethod(lambda i: i in \
                                              restriction_arg)
        self._restriction_arg = restriction_arg
        self._restriction_type = restriction_type
      else:
        raise TypeError, "unsupported restriction type"
      if not val == False:
        if not self._restriction_test(val):
          raise ValueError, "did not match restricted type"
      obj = base_type.__new__(self, *args, **kwargs)
      return obj

    def __check(self, v):
      """
        Run the _restriction_test static method against the argument v,
        returning an error if the value does not validate.
      """
      v = base_type(v)
      if not self._restriction_test(v):
        raise ValueError, "did not match restricted type"
      return True

    def getValue(self, *args, **kwargs):
      """
        For types where there is a dict_key restriction (such as YANG
        enumeration), return the value of the dictionary key.
      """
      if self._restriction_type == "dict_key":
        value = kwargs.pop("mapped", False)
        if value:
          return self._restriction_arg[self.__str__()]["value"]
      return self

  return type(RestrictedClass(*args, **kwargs))

def TypedListType(*args, **kwargs):
  allowed_type = kwargs.pop("allowed_type", str)
  if not isinstance(allowed_type, list):
    allowed_type = [allowed_type,]
  # this was from collections.MutableSequence
  class TypedList(collections.MutableSequence):

    def __init__(self, *args, **kwargs):
      self._allowed_type = allowed_type
      self._list = list()
      if len(args):
        for i in args[0]:
          self.check(i)
        self._list.extend(args[0])

    def check(self,v):
      passed = False
      for i in self._allowed_type:
        if isinstance(v, i):
          passed = True
        try:
          # specific checks are required where there is a
          # restricted class, so we generate a tmp type to
          # be able to check the __bases__ of.
          tmp_t = RestrictedClassType(base_type=str, restriction_type="pattern", restriction_arg=".*")
          if i.__bases__ == tmp_t.__bases__:
            tmp = i(v)
            passed = True
            break
          elif i in NUMPY_INTEGER_TYPES:
            # numpy has odd characteristics where
            # it supports lists, so we check against
            # int as well.
            tmp = int(v)
            tmp = i(v)
            passed = True
            break
        except:
            pass
      if not passed:
        raise ValueError("Cannot add %s to TypedList (accepts only %s)" % \
          (v, self._allowed_type))

    def __len__(self): return len(self._list)
    def __getitem__(self, i): return self._list[i]
    def __delitem__(self, i): del self._list[i]
    def __setitem__(self, i, v):
      self.check(v)
      self._list.insert(i,v)

    def insert(self, i, v):
      self.check(v)
      self._list.insert(i,v)

    def append(self, v):
      self.check(v)
      self._list.append(v)

    def __str__(self):
      return str(self._list)

    def __iter__(self):
      return iter(self._list)

    def __eq__(self, other):
      if self._list == other:
        return True
      return False

    def get(self, filter=False):
      return self._list
  return type(TypedList(*args,**kwargs))

def YANGListType(*args,**kwargs):
  try:
    keyname = args[0]
    listclass = args[1]
  except:
    raise TypeError, "A YANGList must be specified with a key value and a contained class"
  is_container = kwargs.pop("is_container", False)
  parent = kwargs.pop("parent", False)
  yang_name = kwargs.pop("yang_name", False)
  user_ordered = kwargs.pop("user_ordered", False)
  path_helper = kwargs.pop("path_helper", False)
  class YANGList(object):
    __slots__ = ('_members', '_keyval', '_contained_class', '_path_helper')
    def __init__(self, *args, **kwargs):
      if user_ordered:
        self._members = collections.OrderedDict()
      else:
        self._members = dict()
      self._keyval = keyname
      if not type(listclass) == type(int):
        raise ValueError, "contained class of a YANGList must be a class"
      self._contained_class = listclass
      self._path_helper = path_helper

    def __str__(self):
      return str(self._members)

    def __repr__(self):
      return repr(self._members)

    def __check__(self, v):
      if self._contained_class is None:
        return False
      if not type(v) == type(self._contained_class):
        return False
      return True

    def __iter__(self):
      return iter(self._members)

    def __contains__(self,k):
      if k in self._members:
        return True
      return False

    def __getitem__(self, k):
      return self._members[k]

    def __setitem__(self, k, v):
      self.__set(k,v)

    def __set(self, k=False, v=False):
      if v and not self.__check__(v):
        raise ValueError, "value must be set to an instance of %s" % \
          (self._contained_class)
      if self._keyval:
        try:
          tmp = YANGDynClass(base=self._contained_class, parent=parent, yang_name=yang_name,
                              is_container=is_container, path_helper=False)
          if " " in self._keyval:
            keys = self._keyval.split(" ")
            keyparts = k.split(" ")
            if not len(keyparts) == len(keys):
              raise KeyError, "YANGList key must contain all key elements (%s)" % (self._keyval.split(" "))
            path_keystring = "["
            for kv,kp in zip(keys,keyparts):
              kv_obj = getattr(tmp, kv)
              path_keystring += "%s='%s' " % (kv_obj.yang_name(),kp)
            path_keystring = path_keystring.rstrip(" ")
            path_keystring += "]"
          else:
            keys = [self._keyval,]
            keyparts = [k,]
            kv_obj = getattr(tmp, self._keyval)
            path_keystring = "[%s=%s]" % (kv_obj.yang_name(), k)
          tmp = YANGDynClass(base=self._contained_class, parent=parent, yang_name=yang_name, \
                  is_container=is_container, path_helper=path_helper, \
                  register_path=self._parent.path()+"/"+self._yang_name+path_keystring)
          for i in range(0,len(keys)):
            key = getattr(tmp, "_set_%s" % keys[i])
            key(keyparts[i])
          self._members[k] = tmp
        except ValueError, m:
          raise KeyError, "key value must be valid, %s" % m
      else:
        # this is a list that does not have a key specified, and hence
        # we generate a uuid that is used as the key, the method then
        # returns the uuid for the upstream process to use
        k = str(uuid.uuid1())
        self._members[k] = YANGDynClass(base=self._contained_class, parent=parent, yang_name=yang_name, \
                            is_container=is_container, path_helper=path_helper)
        return k

    def __delitem__(self, k):
      del self._members[k]

    def __len__(self): return len(self._members)

    def keys(self): return self._members.keys()

    def add(self, k=False):
      if k in self._members:
        raise KeyError, "%s is already defined as a list entry" % k
      if self._keyval:
        if not k:
          raise KeyError, "a list with a key value must have a key specified"
        self.__set(k)
      else:
        k = self.__set()
        return k

    def delete(self, k):
      if self._path_helper:
        current_item = self._members[k]
        keyparts = self._keyval.split(" ")

        keyargs = k.split(" ")
        key_string = "["
        for key,val in zip(keyparts,keyargs):
          key_string += "%s=%s " % (key,val)
        key_string = key_string.rstrip(" ")
        key_string += "]"

        obj_path = self._parent.path() + "/" + self._yang_name + key_string

      try:
        del self._members[k]
        if self._path_helper:
          self._path_helper.unregister(obj_path)
      except KeyError, m:
        raise KeyError, "key %s was not in list (%s)" % (k,m)

    def get(self, filter=False):
      if user_ordered:
        d = collections.OrderedDict()
      else:
        d = {}
      for i in self._members:
        if hasattr(self._members[i], "get"):
          d[i] = self._members[i].get(filter=filter)
        else:
          d[i] = self._members[i]
      return d

  return type(YANGList(*args,**kwargs))

class YANGBool(int):
  def __new__(self, *args, **kwargs):
    false_args = ["false", "False", False, 0, "0"]
    true_args = ["true", "True", True, 1, "1"]
    if len(args):
      if not args[0] in false_args + true_args:
        raise ValueError, "%s is an invalid value for a YANGBool" % args[0]
      value = 0 if args[0] in false_args else 1
    else:
      value = 0
    return int.__new__(self, bool(value))

  def __repr__(self):
    return str([False, True][self])

  def __str__(self):
    return str(self.__repr__())

def YANGDynClass(*args,**kwargs):
  base_type = kwargs.pop("base", False)
  default = kwargs.pop("default", False)
  yang_name = kwargs.pop("yang_name", False)
  parent_instance = kwargs.pop("parent", False)
  choice_member = kwargs.pop("choice", False)
  is_container = kwargs.pop("is_container", False)
  is_leaf = kwargs.pop("is_leaf", False)
  path_helper = kwargs.pop("path_helper", False)
  supplied_register_path = kwargs.pop("register_path", None)
  if not base_type:
    raise TypeError, "must have a base type"
  if base_type in NUMPY_INTEGER_TYPES and len(args):
    if isinstance(args[0], list):
      raise TypeError, "do not support creating numpy ndarrays!"
  if isinstance(base_type, list):
    # this is a union, we must infer type
    if not len(args):
      # there is no argument to infer the type from
      # so use the first type (default)
      base_type = base_type[0]
    else:
      type_test = False
      for candidate_type in base_type:
        try:
          type_test = candidate_type(args[0]) # does the slipper fit?
          break
        except:
          pass # don't worry, move on, plenty more fish (types) in the sea...
      if not type_test:
        # we're left alone at midnight -- no types fit the arguments
        raise TypeError, "did not find a valid type using the argument as a" + \
                            "hint"
      # otherwise, hop, skip and jump with the last candidate
      base_type = candidate_type

  class YANGBaseClass(base_type):
    if is_container:
      __slots__ = ('_default', '_changed', '_yang_name', '_choice', '_parent', '_supplied_register_path',
                   '_path_helper', '_base_type', '_is_leaf', '_is_container')
    def __new__(self, *args, **kwargs):
      obj = base_type.__new__(self, *args, **kwargs)
      return obj

    def __init__(self, *args, **kwargs):
      self._default = False
      self._changed = False
      self._yang_name = yang_name
      self._parent = parent_instance
      self._choice = choice_member
      self._path_helper = path_helper
      self._supplied_register_path = supplied_register_path
      self._base_type = base_type
      self._is_leaf = is_leaf
      self._is_container = is_container
      if self._path_helper:
        if self._supplied_register_path is None:
          self._path_helper.register(self._register_path(), self)
        else:
          self._path_helper.register(self._supplied_register_path, self)
      if default:
        self._default = default
      if len(args):
        if not args[0] == self._default:
          self._changed = True

      try:
        super(YANGBaseClass, self).__init__(*args, **kwargs)
      except:
        raise TypeError, "couldn't generate dynamic type"

    def changed(self):
      return self._changed

    def path(self):
      return self._register_path()

    def __str__(self):
      return super(YANGBaseClass, self).__str__()

    def repr(self):
      return super(YANGBaseClass, self).__str__()

    def set(self,choice=False):
      if hasattr(self, '__choices__') and choice:
        for ch in self.__choices__:
          if ch == choice[0]:
            for case in self.__choices__[ch]:
              if not case == choice[1]:
                for elem in self.__choices__[ch][case]:
                  method = "_unset_%s" % elem
                  if not hasattr(self, method):
                    raise AttributeError, "unmapped choice!"
                  x = getattr(self, method)
                  x()
      if self._choice and not choice:
        choice=self._choice
      self._changed = True
      if self._parent and hasattr(self._parent, "set"):
        self._parent.set(choice=choice)

    def yang_name(self):
      return self._yang_name

    def default(self):
      return self._default

    # we need to overload the set methods
    def __setitem__(self, *args, **kwargs):
      self._changed = True
      super(YANGBaseClass, self).__setitem__(*args, **kwargs)

    def _register_path(self):
      if not self._supplied_register_path is None:
        return self._supplied_register_path
      if not self._parent is None:
        return self._parent.path() + "/" + self._yang_name
      else:
        return "/"

    def append(self, *args, **kwargs):
      if not hasattr(super(YANGBaseClass,self), "append"):
        raise AttributeError("%s object has no attribute append" % base_type)
      self.set()
      super(YANGBaseClass, self).append(*args,**kwargs)
      if self._path_helper:
        register_path = self._register_path() + "/" + str(args[0])
        super_class = super(YANGBaseClass, self)
        self._path_helper.register(register_path, super_class.__getitem__(super_class.__len__()-1))

    def pop(self, *args, **kwargs):
      if not hasattr(super(YANGBaseClass, self), "pop"):
        raise AttributeError("%s object has no attribute pop" % base_type)
      self.set()
      item = super(YANGBaseClass, self).pop(*args, **kwargs)
      # TODO: remove element from helper
      if self._path_helper:
        register_path = self._register_path() + "/" + str(item)
        self._path_helper.unregister(register_path)
      return item

    def remove(self, *args, **kwargs):
      if not hasattr(super(YANGBaseClass, self), "remove"):
        raise AttributeError("%s object has no attribute remove" % base_type)
      self.set()
      if self._path_helper:
        elem_index = super(YANGBaseClass, self).index(*args, **kwargs)
        item = super(YANGBaseClass, self).__getitem__(elem_index)
      super(YANGBaseClass, self).remove(*args, **kwargs)
      if self._path_helper:
        register_path = self._register_path() + "/" + str(item)
        self._path_helper.unregister(register_path)

    def extend(self, *args, **kwargs):
      if not hasattr(super(YANGBaseClass, self), "extend"):
        raise AttributeError("%s object has no attribute extend" % base_type)
      self.set()
      super(YANGBaseClass, self).extend(*args, **kwargs)
      # Note we do not call register() here for a path_helper as extend()
      # will call append.

    def insert(self, *args, **kwargs):
      if not hasattr(super(YANGBaseClass,self), "insert"):
        raise AttributeError("%s object has no attribute insert" % base_type)
      self.set()
      super(YANGBaseClass, self).insert(*args, **kwargs)
      if self._path_helper:
        register_path = self._register_path() + "/" + str(args[1])
        self._path_helper.register(register_path, super(YANGBaseClass, self).__getitem__(args[0]))

  return YANGBaseClass(*args, **kwargs)

def ReferenceType(*args,**kwargs):
  ref_path = kwargs.pop("referenced_path", False)
  path_helper = kwargs.pop("path_helper", False)
  caller = kwargs.pop("caller", False)
  require_instance = kwargs.pop("require_instance", False)
  class ReferencePathType(object):

    def __init__(self, *args, **kwargs):
      self._referenced_path = ref_path
      self._path_helper = path_helper
      self._referenced_object = False
      self._caller = caller
      self._ptr = False
      self._require_instance = require_instance

      if len(args):
        value = args[0]
      else:
        value = None

      if self._path_helper:
        path_chk = self._path_helper.get(self._referenced_path, caller=self._caller)

        if len(path_chk) == 1 and path_chk[0]._is_leaf == True:
          # we are not checking whether this leaf exists, but rather
          # this is a pointer to some other value.
          if value:
            path_parts = self._referenced_path.split("/")
            leaf_name = path_parts[len(path_parts)-1]
            set_method = getattr(path_chk[0]._parent, "_set_%s" % leaf_name)
            set_method(value)
          self._ptr = True
        elif self._require_instance:
          if not value:
            self._referenced_object = None
          elif self._require_instance:
            lookup_o = []
            path_chk = self._path_helper.get(self._referenced_path, caller=self._caller)

            found = False
            if value in path_chk:
              self._referenced_object = path_chk[path_chk.index(value)]
              found = True
            else:
              for i in path_chk:
                try:
                  self._referenced_object = i[i.index(value)]
                  found = True
                except ValueError:
                  pass
            if not found:
              raise ValueError, "no such key (%s) existed in path (%s -> %s)" % (value, self._referenced_path, path_chk)
        else:
          # require instance is not set, so act like a string
          self._referenced_object = value

    def _get_ptr(self):
      if self._ptr:
        ptr = self._path_helper.get(self._referenced_path, caller=self._caller)
        if len(ptr) == 1:
          return ptr[0]
      raise ValueError, "Invalid pointer specified"

    def __repr__(self):
      if not self._ptr:
        return repr(self._referenced_object)
      return repr(self._get_ptr())

    def __str__(self):
      if not self._ptr:
        return str(self._referenced_object)
      return str(self._get_ptr())

  return type(ReferencePathType(*args,**kwargs))
