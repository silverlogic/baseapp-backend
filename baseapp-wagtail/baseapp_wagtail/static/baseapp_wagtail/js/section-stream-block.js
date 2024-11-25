class SectionsStreamBlockDefinition extends window.wagtailStreamField.blocks.StreamBlockDefinition {
    render(placeholder, prefix, initialState, initialError) {
        const block = super.render(placeholder, prefix, initialState, initialError);

        const removeButton = (button) => {
            button.style.display = 'none';
        }

        const styleDefaultButton = (button) => {
            button.innerHTML = `Add Section${button.innerHTML}`;
            button.style.display = 'flex';
            button.style.justifyContent = 'start';
            button.style.alignItems = 'center';
            button.style.gap = '8px';
            button.style.width = '100%';
        }

        const fixButtons = (sectionWrapper) => {
            const buttons = sectionWrapper.querySelectorAll(':scope > div > button');
            if (!buttons || buttons.length === 0) return;
            if (buttons.length === 1) {
                return styleDefaultButton(buttons[0]);
            }
            buttons.forEach((button, index) => {
                if (index === buttons.length - 1) {
                    return styleDefaultButton(button);
                }
                removeButton(button);
            })
        }

        const fixHeadings = (sectionWrapper) => {
            const headings = sectionWrapper.querySelectorAll(':scope > div > section > .w-panel__header > .w-panel__heading');
            if (!headings || headings.length === 0) return;
            headings.forEach((heading, index) => {
                const defaultLabel = heading.querySelector('.c-sf-block__type');
                if (defaultLabel) {
                    defaultLabel.textContent = `Section ${index + 1}`;
                    defaultLabel.style.display = 'block !important';
                }
                const dynamicLabel = heading.querySelector('[data-panel-heading-text]'); 
                if (dynamicLabel) {
                    dynamicLabel.remove();
                }
            });
        }

        const observeIterations = (mutationsList, observer) => {
            if (mutationsList.length === 0) return;
            const sectionWrapper = mutationsList[0].target;
            fixButtons(sectionWrapper);
            fixHeadings(sectionWrapper);
        }
        
        const initButtonsMutations = (container) => {
            const streamFieldWrapper = container.querySelector('div[data-streamfield-stream-container]');
            if (!streamFieldWrapper) return;

            fixButtons(streamFieldWrapper);
            fixHeadings(streamFieldWrapper);
            (new MutationObserver(observeIterations)).observe(
                streamFieldWrapper,
                { childList: true }
            );
        }

        Array.from(block.container).forEach((container) => initButtonsMutations(container));

        return block;
    }
}


window.telepath.register(
    "baseapp_wagtail.stream_blocks.SectionStreamBlock",
    SectionsStreamBlockDefinition
);
