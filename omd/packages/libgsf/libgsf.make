LIBGSF := libgsf

LIBGSF_BUILD := $(BUILD_HELPER_DIR)/$(LIBGSF)-build
LIBGSF_INTERMEDIATE_INSTALL := $(BUILD_HELPER_DIR)/$(LIBGSF)-install-intermediate
LIBGSF_INSTALL := $(BUILD_HELPER_DIR)/$(LIBGSF)-install

LIBGSF_INSTALL_DIR := $(INTERMEDIATE_INSTALL_BASE)/$(LIBGSF)
LIBGSF_BUILD_DIR := $(PACKAGE_BUILD_DIR)/$(LIBGSF)

.PHONY: $(LIBGSF_BUILD)
$(LIBGSF_BUILD):
ifneq ($(filter $(DISTRO_CODE),sles15 sles15sp3 sles15sp4 sles15sp5),)
	$(BAZEL_BUILD) @$(LIBGSF)//:$(LIBGSF)
endif

.PHONY: $(LIBGSF_INTERMEDIATE_INSTALL)
$(LIBGSF_INTERMEDIATE_INSTALL): $(LIBGSF_BUILD)
ifneq ($(filter $(DISTRO_CODE),sles15 sles15sp3 sles15sp4 sles15sp5),)
	$(MKDIR) $(LIBGSF_INSTALL_DIR)
	$(RSYNC) --chmod=u+w $(BAZEL_BIN_EXT)/$(LIBGSF)/$(LIBGSF)/ $(LIBGSF_INSTALL_DIR)/
endif

.PHONY: $(LIBGSF_INSTALL)
$(LIBGSF_INSTALL): $(LIBGSF_INTERMEDIATE_INSTALL)
ifneq ($(filter $(DISTRO_CODE),sles15 sles15sp3 sles15sp4 sles15sp5),)
	$(RSYNC) $(LIBGSF_INSTALL_DIR)/ $(DESTDIR)$(OMD_ROOT)/
endif
